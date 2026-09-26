from datetime import datetime
from app.models.orm import TimelineEvent


def add_event(s, case_id, event_type, title, detail=None, locality=None, org_id=None, occurred_at=None):
    ev = TimelineEvent(case_id=case_id, event_type=event_type, title=title, detail=detail,
                       locality=locality, org_id=org_id, occurred_at=occurred_at or datetime.now())
    s.add(ev)
    return ev
