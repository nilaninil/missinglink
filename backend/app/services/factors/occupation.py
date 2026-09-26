"""EXAMPLE FACTOR (disabled by default: weight 0 in match_weights.py).

Shows that adding a new evidence source = this file + one registry line + one weight.
"""
from .base import FactorResult


class OccupationFactor:
    name = "occupation"

    def evaluate(self, p, r, ctx):
        if not p.occupation or not r.occupation:
            return FactorResult(self.name, "unavailable", None, reason="Occupation not recorded on one side.")
        a, b = p.occupation.lower().strip(), r.occupation.lower().strip()
        s = 1.0 if a == b else 0.6 if (a in b or b in a) else 0.1
        return FactorResult(self.name, "available", s, reason=f"Occupation: {p.occupation} vs {r.occupation}.")
