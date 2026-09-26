"""Image embeddings: CLIP ViT-B/32 (local weights) with a deterministic fallback.

The fallback combines spatial HSV colour histograms (head / torso / legs bands)
with an OpenCV HOG shape descriptor, padded to 512-d and L2-normalised. The demo
never breaks because a model failed to load.
"""
import io
import logging
import threading
import numpy as np
import cv2
from PIL import Image, UnidentifiedImageError, ImageOps
from app.config.settings import MODELS_DIR, EMBED_DIM

log = logging.getLogger("missinglink.embedding")


class ImageProcessingError(Exception):
    message = "Unable to process image. Please upload a clearer image."


def load_image(src) -> Image.Image:
    try:
        if isinstance(src, (bytes, bytearray)):
            img = Image.open(io.BytesIO(src))
        elif isinstance(src, Image.Image):
            img = src
        else:
            img = Image.open(src)
        img.load()
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as e:
        raise ImageProcessingError(str(e))


def _l2(v):
    v = np.asarray(v, dtype=np.float32).ravel()
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class FallbackEncoder:
    """Deterministic handcrafted descriptor: foreground-isolated color histograms,
    facial/body texture (LBP + HOG), and Lab color per body band."""
    name = "Fallback visual encoder"
    key = "fallback"
    _hog = cv2.HOGDescriptor((64, 128), (32, 32), (16, 16), (16, 16), 9)

    @staticmethod
    def foreground_mask(rgb):
        h, w = rgb.shape[:2]
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        
        # Border background sample
        border = np.concatenate([lab[:4].reshape(-1, 3), lab[-4:].reshape(-1, 3),
                                 lab[:, :4].reshape(-1, 3), lab[:, -4:].reshape(-1, 3)])
        bgc = np.median(border, axis=0)
        dist = np.linalg.norm(lab - bgc, axis=2)
        
        # Center-weighted person prior (people are in the middle 60% of frame)
        cx, cy = w / 2.0, h * 0.45
        y_coords, x_coords = np.ogrid[:h, :w]
        center_prior = np.exp(-(((x_coords - cx) / (0.42 * w)) ** 2 + ((y_coords - cy) / (0.65 * h)) ** 2))
        
        # Combined mask
        mask = ((dist > 14) | (center_prior > 0.45)).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        
        # Suppress far left/right edges to avoid background wall intrusion
        edge_margin = max(2, int(w * 0.08))
        mask[:, :edge_margin] = 0
        mask[:, -edge_margin:] = 0
        
        if mask.mean() < 0.05 or mask.mean() > 0.95:
            mask = np.ones((h, w), np.uint8)
            mask[:, :int(w * 0.15)] = 0
            mask[:, -int(w * 0.15):] = 0
        return mask

    def embed(self, img: Image.Image) -> np.ndarray:
        rgb = np.asarray(img.resize((96, 192)))
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        mask = self.foreground_mask(rgb)
        
        parts = []
        for y0, y1, wt in ((0.0, 0.28, 0.8), (0.26, 0.65, 1.0), (0.62, 1.0, 0.7)):
            a, b = int(y0 * 192), int(y1 * 192)
            m = mask[a:b]
            if m.sum() < 10:
                m = np.ones_like(m)
            hs = cv2.calcHist([hsv[a:b]], [0, 1], m, [12, 3], [0, 180, 20, 256]).ravel()
            hs = cv2.GaussianBlur(hs.reshape(12, 3).astype(np.float32), (1, 3), 0).ravel()
            vv = cv2.calcHist([hsv[a:b]], [2], m, [6], [0, 256]).ravel()
            
            # Central foreground lab mean (excluding edges)
            px = lab[a:b][m.astype(bool)]
            mean = (px.mean(axis=0) - 128) / 128.0 if len(px) else np.zeros(3)
            parts.append(np.concatenate([np.sqrt(_l2(hs)) * 0.7, 0.4 * np.sqrt(_l2(vv)), 0.6 * mean]) * wt)
            
        gray = cv2.cvtColor(np.asarray(img.resize((64, 128))), cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_eq = clahe.apply(gray)
        hog = self._hog.compute(gray_eq).ravel()
        v = np.concatenate(parts + [_l2(hog) * 0.7])
        out = np.zeros(EMBED_DIM, dtype=np.float32)
        out[:min(len(v), EMBED_DIM)] = v[:EMBED_DIM]
        return _l2(out)



class ClipEncoder:
    name = "CLIP ViT-B/32 (local)"
    key = "clip"

    def __init__(self):
        import torch  # noqa
        import open_clip
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k", cache_dir=str(MODELS_DIR))
        self.model.eval()

    def embed(self, img: Image.Image) -> np.ndarray:
        with self.torch.no_grad():
            x = self.preprocess(img).unsqueeze(0)
            f = self.model.encode_image(x)[0].cpu().numpy()
        return _l2(f)


_encoder = None
_lock = threading.Lock()


def get_encoder():
    global _encoder
    with _lock:
        if _encoder is None:
            import os
            if os.environ.get("MISSINGLINK_FORCE_FALLBACK") == "1":
                _encoder = FallbackEncoder()
            else:
                try:
                    _encoder = ClipEncoder()
                    log.info("CLIP encoder loaded")
                except Exception as e:  # missing torch/open_clip/weights
                    log.warning("CLIP unavailable (%s) - using fallback encoder", e)
                    _encoder = FallbackEncoder()
        return _encoder


def encoder_name() -> str:
    return get_encoder().name


def encoder_key() -> str:
    return get_encoder().key


def embed_image(src) -> np.ndarray:
    img = load_image(src)
    if min(img.size) < 16:
        raise ImageProcessingError("image too small")
    return get_encoder().embed(img)
