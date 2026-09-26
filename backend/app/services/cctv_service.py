"""CCTV processing: sample frames, find people (HOG, then motion), compare with case photo."""
import json
import logging
from datetime import datetime, timedelta
import numpy as np
import cv2
from PIL import Image
from app.config.settings import MEDIA_DIR, CCTV_SAMPLE_FPS, CCTV_MAX_FRAMES, CCTV_MIN_SIMILARITY
from app.services.embedding_service import get_encoder, encoder_key
from app.services.calibration import calibrate
from app.services import gazetteer

log = logging.getLogger("missinglink.cctv")
_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def _sample_frames(path, fps_sample):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("cannot open video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 10
    step = max(1, int(round(fps / fps_sample)))
    frames, i = [], 0
    while len(frames) < CCTV_MAX_FRAMES:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            frames.append((i / fps, cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
        i += 1
    cap.release()
    return frames


def _detections(frame, background):
    boxes = []
    try:
        rects, _ = _hog.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), winStride=(8, 8), scale=1.05)
        boxes = [tuple(map(int, r)) for r in rects]
    except Exception:
        pass
    if not boxes and background is not None:
        diff = cv2.absdiff(frame, background).max(axis=2)
        _, m = cv2.threshold(diff, 28, 255, cv2.THRESH_BINARY)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w * h > 1500 and h > 1.2 * w and y > 30:
                boxes.append((x, y, w, h))
    return boxes


def process(path, case_vec, camera_name, locality, start: datetime, time_scale=1.0, case_id=None,
            last_known=None, fps_sample=CCTV_SAMPLE_FPS):
    frames = _sample_frames(path, fps_sample)
    if not frames:
        raise ValueError("no frames")
    background = np.median(np.stack([f for _, f in frames]), axis=0).astype(np.uint8) if len(frames) >= 5 else None
    enc, key = get_encoder(), encoder_key()
    results = []
    for t, fr in frames:
        best = None
        for (x, y, w, h) in _detections(fr, background):
            pad = int(0.08 * h)
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(fr.shape[1], x + w + pad), min(fr.shape[0], y + h + pad)
            crop = Image.fromarray(fr[y0:y1, x0:x1])
            if crop.size[0] < 16 or crop.size[1] < 32:
                continue
            sim = calibrate(float(enc.embed(crop) @ case_vec), key)
            if best is None or sim > best[0]:
                best = (sim, crop, (x0, y0, x1, y1))
        if best and best[0] >= CCTV_MIN_SIMILARITY:
            results.append((t, best, fr))
    # keep best per 3-second window to avoid near-duplicates
    results.sort(key=lambda r: -r[1][0])
    kept = []
    for r in results:
        if all(abs(r[0] - k[0]) > 3 for k in kept):
            kept.append(r)
    kept.sort(key=lambda r: r[0])
    out = []
    for t, (sim, crop, box), fr in kept[:6]:
        ts = start + timedelta(seconds=t * time_scale)
        stamp = f"{case_id or 'adhoc'}_{int(t*10)}_{datetime.now().strftime('%H%M%S%f')}"
        crop_rel, frame_rel = f"crops/cctv_{stamp}.png", f"crops/cctv_frame_{stamp}.jpg"
        crop.save(MEDIA_DIR / crop_rel)
        fimg = fr.copy()
        cv2.rectangle(fimg, box[:2], box[2:], (255, 200, 0), 3)
        Image.fromarray(fimg).save(MEDIA_DIR / frame_rel, quality=80)
        loc_comp = None
        if last_known:
            km = gazetteer.distance_km(last_known, locality)
            loc_comp = None if km is None else round(float(np.exp(-km / 4)), 3)
        out.append({"camera_name": camera_name, "locality": locality, "frame_datetime": ts.isoformat(),
                    "video_offset_s": round(t, 1), "visual_similarity": round(sim, 4),
                    "location_compatibility": loc_comp, "crop_path": crop_rel, "frame_path": frame_rel,
                    "crop_url": f"/media/{crop_rel}", "frame_url": f"/media/{frame_rel}",
                    "status": "Potential Sighting — Requires Human Verification"})
    return out, len(frames)
