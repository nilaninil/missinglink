import math
from datetime import timedelta
from app.services import gazetteer
from .base import FactorResult

MAX_SPEED_KMH = 60


class TimeFactor:
    name = "time"

    def evaluate(self, p, r, ctx):
        if r.time is None or p.origin.time is None:
            return FactorResult(self.name, "unavailable", None, reason="Time not recorded on one side.")
        if r.time < p.origin.time - timedelta(minutes=5):
            return FactorResult(self.name, "conflict", 0.0,
                                reason=f"Record time {r.time:%d %b %H:%M} is before the person was last seen ({p.origin.time:%H:%M}).")
        anchor = p.anchor_for(r.time)
        hours = max(0.0, (r.time - (anchor.time or p.origin.time)).total_seconds() / 3600)
        km = gazetteer.distance_km(anchor.locality, r.locality)
        if km is not None and hours > 0 and km / max(hours, 1 / 60) > MAX_SPEED_KMH and km > 5:
            return FactorResult(self.name, "conflict", 0.0,
                                reason=f"Travelling {km:.0f} km in {hours*60:.0f} min is implausible.")
        if hours > 72:
            return FactorResult(self.name, "available", 0.05, reason=f"Record is {hours:.0f} h after last known sighting.")
        s = math.exp(-hours / 8)
        mins = hours * 60
        span = f"{mins:.0f} min" if mins < 120 else f"{hours:.1f} h"
        return FactorResult(self.name, "available", s,
                            reason=f"Recorded {span} after last known sighting ({anchor.source}) — plausible timing.")
