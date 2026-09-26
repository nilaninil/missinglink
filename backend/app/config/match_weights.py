"""Single source of truth for matching weights and bands.

Weights do not need to sum to 1: the engine normalises over the factors that are
actually available for a given case/record pair.
"""
import json
from .settings import WEIGHTS_OVERRIDE_PATH

DEFAULT_MATCH_WEIGHTS = {
    "photo": 0.45,
    "age": 0.15,
    "gender": 0.10,
    "clothing": 0.10,
    "location": 0.10,
    "time": 0.10,
    # Direct corroboration from an institutional record (hospital/police) that
    # explicitly links evidence to this record. Set to 0.20 so a hospital log
    # counts as much as age + gender together.
    "corroboration": 0.20,
    # Example factor shipped DISABLED (weight 0). Give it a weight to enable it.
    "occupation": 0.0,
}
BANDS = {"high_priority": 0.80, "possible": 0.60}
MIN_FACTORS_FOR_HIGH_PRIORITY = 3
LOW_QUALITY_PHOTO_WEIGHT_MULTIPLIER = 0.5
SCORE_CAP = 0.99
CRITICAL_CONFLICT_FACTORS = {"gender", "time"}


def get_weights() -> dict:
    w = dict(DEFAULT_MATCH_WEIGHTS)
    if WEIGHTS_OVERRIDE_PATH.exists():
        try:
            data = json.loads(WEIGHTS_OVERRIDE_PATH.read_text())
            w.update({k: float(v) for k, v in data.items() if k in w})
        except Exception:
            pass
    return w


def set_weights(new: dict) -> dict:
    w = get_weights()
    for k, v in new.items():
        if k in w:
            w[k] = max(0.0, min(1.0, float(v)))
    WEIGHTS_OVERRIDE_PATH.write_text(json.dumps(w, indent=2))
    return w


def reset_weights():
    if WEIGHTS_OVERRIDE_PATH.exists():
        WEIGHTS_OVERRIDE_PATH.unlink()
