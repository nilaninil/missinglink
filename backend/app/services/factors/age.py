from .base import FactorResult


class AgeFactor:
    name = "age"

    def evaluate(self, p, r, ctx):
        if p.age_min is None or r.age_min is None:
            return FactorResult(self.name, "unavailable", None, reason="Age not recorded on one side.")
        gap = max(0, r.age_min - p.age_max, p.age_min - r.age_max)
        rng = f"case {p.age_min}–{p.age_max} vs record {r.age_min}–{r.age_max}"
        if gap > 10:
            return FactorResult(self.name, "conflict", 0.0, reason=f"Age ranges {gap} years apart ({rng}).")
        if gap <= 2:
            return FactorResult(self.name, "available", 1.0, reason=f"Age ranges compatible ({rng}).")
        s = max(0.0, 1 - (gap - 2) / 8 * 0.9)
        return FactorResult(self.name, "available", s, reason=f"Age ranges {gap} years apart ({rng}).")
