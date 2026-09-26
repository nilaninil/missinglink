"""Encoder-agnostic calibration of raw cosine similarity to a 0..1 photo score.

Raw cosines differ wildly between encoders (CLIP places most images of people
around 0.7-0.9; the fallback descriptor spreads wider). So at seed time we
measure the cosine between unrelated seeded records ("negative pairs") and use
that as the floor:  score = clamp((cos - floor) / (ceil - floor), 0, 1).
"""
import json
import numpy as np
from app.config.settings import CALIBRATION_PATH

DEFAULTS = {"clip": {"floor": 0.55, "ceil": 0.95}, "fallback": {"floor": 0.45, "ceil": 0.97}}


def compute_and_store(encoder_key: str, vectors: list):
    if len(vectors) < 3:
        return get(encoder_key)
    M = np.stack(vectors)
    S = M @ M.T
    iu = np.triu_indices(len(vectors), 1)
    sims = S[iu]
    floor = float(np.percentile(sims, 60))
    ceil = float(min(0.99, max(floor + 0.15, np.percentile(sims, 99.5) + 0.02)))
    data = {}
    if CALIBRATION_PATH.exists():
        try:
            data = json.loads(CALIBRATION_PATH.read_text())
        except Exception:
            data = {}
    data[encoder_key] = {"floor": round(floor, 4), "ceil": round(ceil, 4)}
    CALIBRATION_PATH.write_text(json.dumps(data, indent=2))
    return data[encoder_key]


def get(encoder_key: str) -> dict:
    if CALIBRATION_PATH.exists():
        try:
            d = json.loads(CALIBRATION_PATH.read_text())
            if encoder_key in d:
                return d[encoder_key]
        except Exception:
            pass
    return DEFAULTS.get(encoder_key, DEFAULTS["fallback"])


def calibrate(cos: float, encoder_key: str) -> float:
    c = get(encoder_key)
    return float(max(0.0, min(1.0, (cos - c["floor"]) / max(1e-6, c["ceil"] - c["floor"]))))
