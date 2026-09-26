from app.services.clothing import color_sim, garment_sim, describe
from .base import FactorResult


class ClothingFactor:
    name = "clothing"

    def evaluate(self, p, r, ctx):
        if not p.clothing_items or not r.clothing_items:
            return FactorResult(self.name, "unavailable", None, reason="Clothing not described on one side.")
        rb = {i["cat"]: i for i in r.clothing_items}
        scores = []
        for it in p.clothing_items:
            o = rb.get(it["cat"])
            if not o:
                continue
            scores.append(0.5 * garment_sim(it["garment"], o["garment"]) + 0.5 * color_sim(it["color"], o["color"]))
        txt = f"{describe(p.clothing_items)} vs {describe(r.clothing_items)}"
        if not scores:
            return FactorResult(self.name, "available", 0.4, reason=f"Different garment types described ({txt}).")
        s = sum(scores) / len(scores)
        word = "consistent" if s >= 0.8 else "partly consistent" if s >= 0.5 else "inconsistent"
        return FactorResult(self.name, "available", s, reason=f"Clothing {word}: {txt}.")
