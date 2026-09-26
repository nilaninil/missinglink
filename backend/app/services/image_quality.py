"""Quality gate: blur (Laplacian variance), low light (mean brightness), resolution."""
import cv2
import numpy as np
from PIL import Image


def assess(img: Image.Image) -> dict:
    arr = np.asarray(img.convert("L"), dtype=np.uint8)
    h, w = arr.shape
    warnings = []
    if min(h, w) < 64:
        return {"quality": "unusable", "warnings": ["Image resolution too low for visual comparison."],
                "blur": 0.0, "brightness": float(arr.mean())}
    blur = float(cv2.Laplacian(arr, cv2.CV_64F).var())
    bright = float(arr.mean())
    q = "good"
    if bright < 25:
        q = "unusable"; warnings.append("Image is almost completely dark.")
    elif bright < 80:
        q = "low"; warnings.append("Photo is low-light.")
    if blur < 12:
        q = "unusable" if blur < 3 else ("low" if q == "good" else q)
        warnings.append("Photo is blurry.")
    if min(h, w) < 160 and q == "good":
        q = "low"; warnings.append("Photo resolution is low.")
    return {"quality": q, "warnings": warnings, "blur": round(blur, 1), "brightness": round(bright, 1)}
