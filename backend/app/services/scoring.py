"""Combine factor results into an evidence score, band and explanation."""
from app.config.match_weights import (BANDS, MIN_FACTORS_FOR_HIGH_PRIORITY, SCORE_CAP,
                                      CRITICAL_CONFLICT_FACTORS)
from app.services.factors import FACTORS

LABELS = {"photo": "Photo similarity", "age": "Age", "gender": "Gender", "clothing": "Clothing",
          "location": "Location", "time": "Time", "corroboration": "Corroborating record",
          "occupation": "Occupation"}
BAND_TEXT = {
    "high_priority": "High-Priority Potential Match",
    "possible": "Potential Match",
    "conflict": "Potential Match — Conflict Detected",
    "low": "Low Evidence",
}


def score_pair(profile, record, ctx) -> dict:
    factors, num, den = [], 0.0, 0.0
    for f in FACTORS:
        w = ctx.weights.get(f.name, 0.0)
        if w <= 0:
            continue
        res = f.evaluate(profile, record, ctx)
        eff = w * res.weight_multiplier
        if res.status in ("available", "conflict"):
            s = res.score or 0.0
            num += s * eff
            den += eff
        factors.append({"name": res.name, "label": LABELS.get(res.name, res.name.title()),
                        "status": res.status, "score": None if res.score is None else round(res.score, 4),
                        "weight": round(w, 3), "effective_weight": round(eff, 3), "reason": res.reason})
    overall = num / den if den > 0 else 0.0
    available = [f for f in factors if f["status"] == "available"]
    conflicts = [f for f in factors if f["status"] == "conflict"]
    unavailable = [f for f in factors if f["status"] == "unavailable"]
    coverage = len(available) + len(conflicts)
    critical = any(c["name"] in CRITICAL_CONFLICT_FACTORS for c in conflicts)

    if overall >= BANDS["high_priority"] and coverage >= MIN_FACTORS_FOR_HIGH_PRIORITY and not conflicts:
        band = "high_priority"
    elif overall >= BANDS["possible"] or (overall >= BANDS["high_priority"]):
        band = "possible"
    else:
        band = "low"
    if critical and band in ("high_priority", "possible"):
        band = "conflict"

    warnings = []
    for f in factors:
        if f["name"] == "photo" and f["effective_weight"] < f["weight"]:
            warnings.append("A photo is low quality — photo weight reduced.")
    reasons = ([{"kind": "support", "text": f["reason"]} for f in available if (f["score"] or 0) >= 0.5] +
               [{"kind": "weak", "text": f["reason"]} for f in available if (f["score"] or 0) < 0.5] +
               [{"kind": "conflict", "text": f["reason"]} for f in conflicts] +
               [{"kind": "missing", "text": f"{f['label']}: Evidence unavailable — excluded from this score."} for f in unavailable])
    total = len(factors)
    return {
        "record_id": record.id,
        "overall_score": round(min(overall, SCORE_CAP), 4),
        "raw_score": round(overall, 4),
        "band": band, "band_text": BAND_TEXT[band], "critical_conflict": critical,
        "status_text": "Requires Human Verification",
        "coverage": coverage,
        "coverage_text": f"Matching using {coverage} of {total} evidence sources",
        "factors": factors,
        "unavailable_list": [f["label"] for f in unavailable],
        "conflicts_list": [f["reason"] for f in conflicts],
        "warnings": warnings,
        "reasons": reasons,
        "enrichments": record.enrichments,
    }
