from app.services.calibration import calibrate
from app.config.match_weights import LOW_QUALITY_PHOTO_WEIGHT_MULTIPLIER
from .base import FactorResult


class PhotoFactor:
    name = "photo"

    def evaluate(self, p, r, ctx):
        if p.photo_vec is None or p.photo_quality == "unusable":
            return FactorResult(self.name, "unavailable", None, reason="No usable photo for the missing person.")
        if r.photo_vec is None or r.photo_quality == "unusable":
            return FactorResult(self.name, "unavailable", None, reason="No usable photo on this record.")
        cos = float(p.photo_vec @ r.photo_vec)
        s = calibrate(cos, ctx.encoder_key)
        mult = 1.0
        why = f"Visual similarity {s:.0%} (raw cosine {cos:.3f})."
        if "low" in (p.photo_quality, r.photo_quality):
            mult = LOW_QUALITY_PHOTO_WEIGHT_MULTIPLIER
            why += " Photo weight halved because one photo is low quality."
        return FactorResult(self.name, "available", s, mult, why)
