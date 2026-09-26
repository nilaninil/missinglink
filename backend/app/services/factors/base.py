from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Protocol
import numpy as np


@dataclass
class FactorResult:
    name: str
    status: Literal["available", "unavailable", "conflict"]
    score: Optional[float]
    weight_multiplier: float = 1.0
    reason: str = ""


@dataclass
class Observation:
    time: Optional[datetime]
    locality: Optional[str]
    source: str


@dataclass
class CaseProfile:
    case_id: str
    name: Optional[str]
    age_min: Optional[int]
    age_max: Optional[int]
    gender: Optional[str]
    clothing_items: list
    origin: Observation                 # original last-seen
    observations: list                  # original + evidence observations after last seen
    photo_vec: Optional[np.ndarray]
    photo_quality: Optional[str]
    occupation: Optional[str] = None
    linked: dict = field(default_factory=dict)   # record_id -> [evidence dicts]
    notes: list = field(default_factory=list)

    @property
    def latest(self) -> Observation:
        timed = [o for o in self.observations if o.time]
        return max(timed, key=lambda o: o.time) if timed else self.origin

    def anchor_for(self, t: Optional[datetime]) -> Observation:
        """Most recent known position at or before time t (falls back to origin)."""
        if t is None:
            return self.latest
        cands = [o for o in self.observations if o.time and o.time <= t and o.locality]
        return max(cands, key=lambda o: o.time) if cands else self.origin


@dataclass
class RecordView:
    """A found record, enriched by evidence explicitly linked to it."""
    id: str
    record_type: str
    age_min: Optional[int]
    age_max: Optional[int]
    gender: Optional[str]
    clothing_items: list
    locality: Optional[str]
    time: Optional[datetime]
    photo_vec: Optional[np.ndarray]
    photo_quality: Optional[str]
    occupation: Optional[str] = None
    enrichments: list = field(default_factory=list)


@dataclass
class MatchContext:
    encoder_key: str
    weights: dict


class Factor(Protocol):
    name: str

    def evaluate(self, profile: CaseProfile, record: RecordView, ctx: MatchContext) -> FactorResult: ...
