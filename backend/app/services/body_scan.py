"""Live body-scan analysis: compares a camera capture (or upload) of a person with the
missing person's reference photo and reports HOW MUCH each part of the evidence agrees.

This is visual-similarity decision support, not biometric identification.

Components:
  appearance   0.30  whole-person embedding similarity (background-isolated)
  face_head    0.25  facial feature similarity (multi-scale LBP texture + facial HOG + skin tone)
  upper        0.20  upper-body clothing colour (dominant colour, Lab distance + histogram)
  lower        0.15  lower-body clothing colour
  silhouette   0.10  body shape / build (HOG silhouette + aspect ratio)
"""
import uuid
import numpy as np
import cv2
from PIL import Image, ImageDraw
from app.config.settings import MEDIA_DIR
from app.config.match_weights import SCORE_CAP
from app.services import image_quality
from app.services.embedding_service import get_encoder, encoder_key, ImageProcessingError
from app.services.calibration import calibrate

WEIGHTS = {"appearance": 0.30, "face_head": 0.25, "upper": 0.20, "lower": 0.15, "silhouette": 0.10}
LABELS = {"appearance": "Overall appearance", "face_head": "Face / head region",
          "upper": "Upper-body clothing", "lower": "Lower-body clothing",
          "silhouette": "Body shape & build"}
REGIONS = {"head": (0.0, 0.24), "upper": (0.24, 0.60), "lower": (0.60, 0.96)}

_hog_people = cv2.HOGDescriptor()
_hog_people.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
_hog_shape = cv2.HOGDescriptor((64, 128), (16, 16), (8, 8), (8, 8), 9)

_cascades = None


def _get_cascades():
    global _cascades
    if _cascades is None:
        _cascades = []
        for name in ["haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"]:
            try:
                p = cv2.data.haarcascades + name
                cas = cv2.CascadeClassifier(p)
                if not cas.empty():
                    _cascades.append(cas)
            except Exception:
                pass
    return _cascades


def _find_face(img_rgb):
    """Find the most prominent face using multi-cascade and lighting equalization."""
    if isinstance(img_rgb, Image.Image):
        img_rgb = np.asarray(img_rgb)
    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_eq = clahe.apply(gray)
    
    candidates = []
    for g in [gray, gray_eq]:
        for cas in _get_cascades():
            for scale in [1.06, 1.12]:
                min_sz = max(18, int(min(h, w) * 0.05))
                rects = cas.detectMultiScale(g, scaleFactor=scale, minNeighbors=3, minSize=(min_sz, min_sz))
                if len(rects):
                    candidates.extend(rects)
                    
    if not candidates:
        return None
        
    best_box = None
    best_score = -1.0
    for (x, y, fw, fh) in candidates:
        cx, cy = x + fw / 2.0, y + fh / 2.0
        dist_c = np.hypot((cx - w / 2.0) / w, (cy - h * 0.4) / h)
        score = (fw * fh) * (1.0 - 0.4 * dist_c)
        if score > best_score:
            best_score = score
            best_box = (int(x), int(y), int(fw), int(fh))
            
    return best_box


def _compute_lbp(gray_img):
    h, w = gray_img.shape
    if h < 3 or w < 3:
        return np.zeros((1, 1), dtype=np.uint8)
    lbp = np.zeros((h - 2, w - 2), dtype=np.uint8)
    for i in range(1, h - 1):
        for j in range(1, w - 1):
            c = gray_img[i, j]
            code = ((gray_img[i-1, j-1] >= c) << 7) | ((gray_img[i-1, j] >= c) << 6) | \
                   ((gray_img[i-1, j+1] >= c) << 5) | ((gray_img[i, j+1] >= c) << 4) | \
                   ((gray_img[i+1, j+1] >= c) << 3) | ((gray_img[i+1, j] >= c) << 2) | \
                   ((gray_img[i+1, j-1] >= c) << 1) | ((gray_img[i, j-1] >= c) << 0)
            lbp[i-1, j-1] = code
    return lbp


def _extract_face_descriptor(face_rgb):
    """Compute lighting-invariant facial texture (LBP), HOG gradients, and facial tone."""
    face_resized = cv2.resize(face_rgb, (96, 96))
    gray = cv2.cvtColor(face_resized, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray_eq = clahe.apply(gray)
    
    # 4x4 grid LBP texture histograms
    bh, bw = 24, 24
    hists = []
    for r in range(4):
        for c in range(4):
            block = gray_eq[r * bh:(r + 1) * bh, c * bw:(c + 1) * bw]
            lbp = _compute_lbp(block)
            h, _ = np.histogram(lbp.ravel(), bins=32, range=(0, 256))
            h = h.astype(np.float32)
            norm = np.linalg.norm(h)
            hists.append(h / (norm + 1e-6))
    lbp_vec = np.concatenate(hists)
    
    # Facial HOG
    hog = cv2.HOGDescriptor((96, 96), (32, 32), (16, 16), (16, 16), 9)
    hog_vec = hog.compute(gray_eq).ravel()
    hog_vec = hog_vec / (np.linalg.norm(hog_vec) + 1e-6)
    
    # Central facial tone (Lab)
    lab = cv2.cvtColor(face_resized, cv2.COLOR_RGB2LAB).astype(np.float32)
    center_lab = lab[20:76, 20:76].reshape(-1, 3)
    tone = (center_lab.mean(axis=0) - 128.0) / 128.0
    
    feat = np.concatenate([lbp_vec * 0.55, hog_vec * 0.40, tone * 0.20])
    return feat / (np.linalg.norm(feat) + 1e-6)


COLOR_NAMES = [
    ("black", (20, 128, 128)), ("white", (245, 128, 128)), ("grey", (135, 128, 128)),
    ("red", (120, 190, 170)), ("maroon", (70, 165, 145)), ("orange", (170, 160, 190)),
    ("yellow", (220, 120, 200)), ("green", (130, 90, 160)), ("blue", (90, 150, 70)),
    ("light blue", (160, 125, 95)), ("navy", (45, 140, 100)), ("pink", (190, 170, 125)),
    ("purple", (90, 165, 90)), ("brown", (100, 145, 160)), ("beige", (200, 132, 150)),
]


def color_name(lab):
    L, a, b = lab
    chroma = np.hypot(a - 128, b - 128)
    if chroma < 12:
        return "black" if L < 60 else "white" if L > 215 else "grey"
    best = min(COLOR_NAMES, key=lambda c: (c[1][0] - L) ** 2 * 0.35 + (c[1][1] - a) ** 2 + (c[1][2] - b) ** 2)
    return best[0]


def _fg_box(rgb, strip_horizontal=False):
    """Largest person-shaped foreground blob."""
    h, w = rgb.shape[:2]
    if h < 40 or w < 20:
        return None
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = np.concatenate([lab[:4].reshape(-1, 3), lab[-4:].reshape(-1, 3),
                             lab[:, :4].reshape(-1, 3), lab[:, -4:].reshape(-1, 3)])
    bgc = np.median(border, axis=0)
    dist = np.linalg.norm(lab - bgc, axis=2)
    mask = (dist > 15).astype(np.uint8)
    if mask.mean() > 0.92 or mask.mean() < 0.02:
        return None
    mask = mask.copy()
    if strip_horizontal and w >= 200:
        smooth = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 15), np.uint8))
        horiz = cv2.morphologyEx(smooth, cv2.MORPH_OPEN, np.ones((1, int(0.75 * w)), np.uint8))
        mask[horiz > 0] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    k = max(3, int(min(h, w) * 0.02)) | 1
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k * 2 + 1, k), np.uint8))
    n, lab_img, stats, _ = cv2.connectedComponentsWithStats(closed, 8)
    best, best_score = None, 0
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bh < 0.20 * h or bw > 0.92 * w or area < 0.02 * h * w:
            continue
        aspect = bh / max(1, bw)
        cx = (x + bw / 2) / w
        centre = 1.0 - 0.6 * abs(cx - 0.5)
        score = area * (1.6 if 1.2 <= aspect <= 5 else 0.5) * centre
        if score > best_score:
            best, best_score = (int(x), int(y), int(x + bw), int(y + bh)), score
    if best is None:
        return None
    x0, y0, x1, y1 = best
    if (x1 - x0) > 0.97 * w and (y1 - y0) > 0.97 * h:
        return None
    return best


def detect_person(img: Image.Image):
    """Return (crop, box, method). Tries face anchor first, then HOG, then foreground segmentation."""
    rgb = np.asarray(img)
    h, w = rgb.shape[:2]
    
    # 1. Check for face anchor (for real human photos and webcam captures)
    face = _find_face(rgb)
    if face is not None:
        fx, fy, fw, fh = face
        cx = fx + fw / 2.0
        pad_x = int(1.4 * fw)
        pad_y_top = int(0.35 * fh)
        pad_y_bot = int(6.5 * fh)
        
        x0 = max(0, int(cx - pad_x))
        x1 = min(w, int(cx + pad_x))
        y0 = max(0, int(fy - pad_y_top))
        y1 = min(h, int(fy + pad_y_bot))
        
        if (x1 - x0) > 30 and (y1 - y0) > 40:
            box = (x0, y0, x1, y1)
            return img.crop(box), box, "facial feature anchor"

    # 2. HOG person detector
    scale = 640 / max(h, w) if max(h, w) > 640 else 1.0
    small = cv2.resize(rgb, (int(w * scale), int(h * scale))) if scale != 1 else rgb
    try:
        rects, weights = _hog_people.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY),
                                                      winStride=(8, 8), padding=(8, 8), scale=1.05)
        if len(rects):
            i = int(np.argmax([r[2] * r[3] for r in rects]))
            x, y, bw, bh = [int(v / scale) for v in rects[i]]
            if bh > 0.35 * h:
                pad = int(0.06 * bh)
                box = (max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad))
                return img.crop(box), box, "HOG person detector"
    except Exception:
        pass

    # 3. Foreground segmentation
    box = (0, 0, w, h)
    found = False
    for i in range(2):
        sub = rgb[box[1]:box[3], box[0]:box[2]]
        nb = _fg_box(sub, strip_horizontal=(i == 0))
        if nb is None:
            break
        box = (box[0] + nb[0], box[1] + nb[1], box[0] + nb[2], box[1] + nb[3])
        found = True
    if found:
        return img.crop(box), box, "foreground segmentation"
        
    return img, (0, 0, w, h), "full frame (no person box found)"


def _region(arr, key):
    h, w = arr.shape[:2]
    y0, y1 = REGIONS[key]
    x0, x1 = int(0.18 * w), int(0.82 * w)
    return arr[int(y0 * h):int(y1 * h), x0:x1]


def _dominant(region_rgb):
    px = region_rgb.reshape(-1, 3).astype(np.float32)
    tot = px.sum(axis=1)
    keep = tot > 20
    if keep.sum() < 10:
        keep = np.ones(len(px), bool)
    px, tot = px[keep], tot[keep] + 1e-3
    chrom = px[:, :2] / tot[:, None]
    feat = np.concatenate([chrom, (tot / (3 * 255))[:, None] * 0.15], axis=1).astype(np.float32)
    k = 3 if len(feat) > 30 else 1
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1e-4)
    _, labels, _ = cv2.kmeans(feat, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    idx = labels.ravel() == int(np.argmax(np.bincount(labels.ravel(), minlength=k)))
    return chrom[idx].mean(axis=0), float(tot[idx].mean()), px[idx].mean(axis=0)


def _display_name(rgb_mean, rel_light):
    c = np.asarray(rgb_mean, np.float32)
    target = np.clip(rel_light, 0.08, 1.6) * 150
    c = np.clip(c * (target / max(1.0, c.mean())), 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(c.reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0].astype(float)
    return color_name(lab)


def _normalise_light(rgb):
    rgb = np.ascontiguousarray(rgb)
    if rgb.mean() < 110:
        rgb = cv2.bilateralFilter(rgb, 5, 30, 5)
        gain = 150.0 / max(20.0, float(np.percentile(rgb, 90)))
        rgb = np.clip(rgb.astype(np.float32) * min(gain, 3.5), 0, 255).astype(np.uint8)
    return rgb


def _region_score(ref, scan, key):
    r, s = _region(ref, key), _region(scan, key)
    if r.size == 0 or s.size == 0:
        return None, "Region not visible."
    cr, lr, mr = _dominant(r)
    cs, ls, ms = _dominant(s)
    rel_r = lr / (ref.reshape(-1, 3).sum(axis=1).mean() + 1e-3)
    rel_s = ls / (scan.reshape(-1, 3).sum(axis=1).mean() + 1e-3)
    dchrom = float(np.linalg.norm(cr - cs))
    dlight = abs(np.log((rel_r + 0.05) / (rel_s + 0.05)))
    color_sim = max(0.0, 1.0 - np.hypot(dchrom / 0.14, dlight / 1.3))
    hr = cv2.calcHist([cv2.cvtColor(r, cv2.COLOR_RGB2HSV)], [0, 1], None, [16, 3], [0, 180, 20, 256])
    hs = cv2.calcHist([cv2.cvtColor(s, cv2.COLOR_RGB2HSV)], [0, 1], None, [16, 3], [0, 180, 20, 256])
    cv2.normalize(hr, hr); cv2.normalize(hs, hs)
    hist_sim = max(0.0, float(cv2.compareHist(hr, hs, cv2.HISTCMP_CORREL)))
    score = float(0.65 * color_sim + 0.35 * hist_sim)
    nr, ns = _display_name(mr, rel_r), _display_name(ms, rel_s)
    return score, f"Reference {nr} vs scan {ns} (colour agreement {color_sim:.0%}, pattern agreement {hist_sim:.0%})."


def _face_head(ref_img, scan_img, ref_n, scan_n):
    fr = _find_face(np.asarray(ref_img))
    fs = _find_face(np.asarray(scan_img))
    
    if fr is not None and fs is not None:
        def crop_face(img, f):
            x, y, w, h = f
            pad_x = int(0.20 * w)
            pad_y = int(0.20 * h)
            im_rgb = np.asarray(img)
            ih, iw = im_rgb.shape[:2]
            return im_rgb[max(0, y - pad_y):min(ih, y + h + pad_y),
                          max(0, x - pad_x):min(iw, x + w + pad_x)]
                          
        face_r = crop_face(ref_img, fr)
        face_s = crop_face(scan_img, fs)
        
        if face_r.size > 0 and face_s.size > 0:
            desc_r = _extract_face_descriptor(face_r)
            desc_s = _extract_face_descriptor(face_s)
            cos_sim = float(desc_r @ desc_s)
            
            sc = min(0.99, max(0.0, (cos_sim - 0.35) / 0.55))
            return float(sc), f"Faces detected in both images; facial feature visual similarity {sc:.0%} (decision support).", "face"
            
    # Fallback to head region comparison
    s, why = _region_score(ref_n, scan_n, "head")
    if s is None:
        return None, "Face / head region not visible.", "none"
    note = "Face not detected in " + ("either image" if not fr and not fs else
                                      "the reference" if not fr else "the scan")
    return s, f"{note}; compared head region contour/hair instead. {why}", "head"


def _silhouette(ref_crop, scan_crop):
    def desc(im):
        g = cv2.cvtColor(np.asarray(im.resize((64, 128))), cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        g_eq = clahe.apply(g)
        v = _hog_shape.compute(g_eq).ravel()
        return v / (np.linalg.norm(v) + 1e-6)
    cos = float(desc(ref_crop) @ desc(scan_crop))
    ar_r = ref_crop.size[0] / max(1, ref_crop.size[1])
    ar_s = scan_crop.size[0] / max(1, scan_crop.size[1])
    ar_sim = max(0.0, 1 - abs(ar_r - ar_s) / max(ar_r, ar_s))
    shape = max(0.0, min(1.0, (cos - 0.38) / 0.50))
    s = float(0.7 * shape + 0.3 * ar_sim)
    return s, f"Silhouette agreement {shape:.0%}; build proportion agreement {ar_sim:.0%}."


def _annotate(crop: Image.Image, name: str):
    im = crop.copy().convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    colors = {"head": (242, 169, 0), "upper": (0, 150, 136), "lower": (90, 110, 200)}
    for key, (y0, y1) in REGIONS.items():
        d.rectangle((int(0.18 * w), int(y0 * h), int(0.82 * w), int(y1 * h) - 1), outline=colors[key], width=max(2, w // 120))
    rel = f"crops/{name}.png"
    im.thumbnail((360, 540))
    im.save(MEDIA_DIR / rel)
    return f"/media/{rel}"


def analyse(ref_img: Image.Image, scan_img: Image.Image) -> dict:
    rq, sq = image_quality.assess(ref_img), image_quality.assess(scan_img)
    if rq["quality"] == "unusable":
        raise ImageProcessingError("reference unusable")
    if sq["quality"] == "unusable":
        raise ImageProcessingError("scan unusable")
    ref_crop, rbox, rmethod = detect_person(ref_img)
    scan_crop, sbox, smethod = detect_person(scan_img)
    size = (120, 280)
    ref_n = _normalise_light(np.asarray(ref_crop.resize(size)))
    scan_n = _normalise_light(np.asarray(scan_crop.resize(size)))

    comps = {}
    enc = get_encoder()
    cos = float(enc.embed(ref_crop) @ enc.embed(scan_crop))
    app_s = min(0.99, max(0.0, (cos - 0.45) / 0.50))
    comps["appearance"] = (app_s, f"Person visual representation similarity {app_s:.0%} using {enc.name} (raw cosine {cos:.3f}).")
    
    fh, why, face_mode = _face_head(ref_crop, scan_crop, ref_n, scan_n)
    comps["face_head"] = (fh, why)
    
    for key in ("upper", "lower"):
        comps[key] = _region_score(ref_n, scan_n, key)
        
    comps["silhouette"] = _silhouette(ref_crop, scan_crop)

    num = den = 0.0
    components = []
    low_q = "low" in (rq["quality"], sq["quality"])
    for k, w in WEIGHTS.items():
        s, reason = comps[k]
        mult = 0.85 if (low_q and k in ("appearance", "face_head")) else 1.0
        if k == "face_head" and face_mode == "face":
            mult = 1.3
        status = "unavailable" if s is None else "available"
        if s is not None:
            num += s * w * mult
            den += w * mult
        components.append({"name": k, "label": LABELS[k], "score": None if s is None else round(s, 4),
                           "weight": w, "effective_weight": round(w * mult, 3), "status": status, "reason": reason})
    overall = num / den if den else 0.0
    avail = [c for c in components if c["status"] == "available"]
    
    if overall >= 0.75 and len(avail) >= 4:
        band, band_text = "high_priority", "High-Priority Potential Match"
    elif overall >= 0.55:
        band, band_text = "possible", "Potential Match"
    else:
        band, band_text = "low", "Low Evidence"
        
    strong = [c["label"].lower() for c in avail if c["score"] >= 0.65]
    weak = [c["label"].lower() for c in avail if c["score"] < 0.45]
    summary = f"The scan agrees with the reference photo to an estimated {min(overall, SCORE_CAP):.0%} across {len(avail)} of {len(components)} visual checks."
    if strong:
        summary += " Strongest agreement: " + ", ".join(strong) + "."
    if weak:
        summary += " Weak or differing: " + ", ".join(weak) + "."
        
    uid = uuid.uuid4().hex[:10]
    warnings = rq["warnings"] + sq["warnings"]
    if low_q:
        warnings.append("One image is low quality — appearance and face weights adjusted.")
    if face_mode != "face":
        warnings.append("Face detection used contour/head region estimation.")
    return {
        "overall_score": round(min(overall, SCORE_CAP), 4), "band": band, "band_text": band_text,
        "status_text": "Requires Human Verification", "summary": summary,
        "components": components, "coverage_text": f"Using {len(avail)} of {len(components)} visual checks",
        "reference": {"quality": rq, "detection": rmethod, "crop_url": _annotate(ref_crop, f"ref_{uid}")},
        "scan": {"quality": sq, "detection": smethod, "crop_url": _annotate(scan_crop, f"scan_{uid}")},
        "warnings": warnings, "encoder": enc.name,
        "disclaimer": "This is a potential visual similarity for authorised investigation, not automatic identification.",
    }
