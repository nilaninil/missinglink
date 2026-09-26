from .base import FactorResult

RELIABILITY = {"hospital": 0.95, "police": 0.95, "shelter": 0.85, "ngo": 0.85, "investigator": 0.8, "public": 0.6}


class CorroborationFactor:
    name = "corroboration"

    def evaluate(self, p, r, ctx):
        ev = p.linked.get(r.id)
        if not ev:
            return FactorResult(self.name, "unavailable", None, reason="No evidence directly links to this record.")
        best, why = 0.0, ""
        for e in ev:
            s = RELIABILITY.get(e.get("org_type") or "", 0.7)
            if e.get("needs_verification"):
                s = min(s, 0.6)
            if s > best:
                best, why = s, f"{e['label']} from {e.get('org_name') or 'a partner'} directly references this record."
        return FactorResult(self.name, "available", best, reason=why)
