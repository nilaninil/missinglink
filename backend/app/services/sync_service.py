"""Simulated regional hub sync: copies pending rows into a second local SQLite file (hub.db)."""
import sqlite3
from datetime import datetime
from app.config.settings import HUB_DB_PATH
from app.models.orm import MissingCase, FoundRecord, Evidence
from app.services import timeline

TABLES = [(MissingCase, "missing_cases"), (FoundRecord, "found_records"), (Evidence, "evidence")]


def pending(s):
    return {name: s.query(M).filter(M.sync_status == "pending_sync").count() for M, name in TABLES}


def run(s):
    con = sqlite3.connect(HUB_DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS hub_rows (tbl TEXT, row_id TEXT, payload TEXT, synced_at TEXT, PRIMARY KEY (tbl, row_id))")
    n = 0
    for M, name in TABLES:
        for row in s.query(M).filter(M.sync_status == "pending_sync").all():
            payload = {c.name: str(getattr(row, c.name)) for c in M.__table__.columns}
            con.execute("INSERT OR REPLACE INTO hub_rows VALUES (?,?,?,?)",
                        (name, str(row.id), repr(payload), datetime.now().isoformat()))
            row.sync_status = "synced"
            n += 1
    con.commit(); con.close()
    if n:
        timeline.add_event(s, None, "sync", "Synced to regional coordination hub",
                           f"{n} record(s) copied to the regional hub (local hub.db).")
    s.commit()
    return n


def hub_count():
    if not HUB_DB_PATH.exists():
        return 0
    con = sqlite3.connect(HUB_DB_PATH)
    try:
        return con.execute("SELECT COUNT(*) FROM hub_rows").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()
