from .base import FactorResult


class GenderFactor:
    name = "gender"

    def evaluate(self, p, r, ctx):
        if not p.gender or not r.gender:
            return FactorResult(self.name, "unavailable", None, reason="Gender not recorded on one side.")
        if p.gender.lower() == r.gender.lower():
            return FactorResult(self.name, "available", 1.0, reason=f"Gender consistent ({r.gender}).")
        return FactorResult(self.name, "conflict", 0.0, reason=f"Gender differs ({p.gender} vs {r.gender}).")
