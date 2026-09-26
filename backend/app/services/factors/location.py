import math
from app.services import gazetteer
from .base import FactorResult


class LocationFactor:
    name = "location"

    def evaluate(self, p, r, ctx):
        anchor = p.anchor_for(r.time)
        km = gazetteer.distance_km(anchor.locality, r.locality)
        if km is None:
            return FactorResult(self.name, "unavailable", None, reason="Locality unknown on one side.")
        s = math.exp(-km / 4)
        return FactorResult(self.name, "available", s,
                            reason=f"{r.locality} is {km:.1f} km from last known location ({anchor.locality}, {anchor.source}).")
