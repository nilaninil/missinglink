"""Shared fixtures: an isolated temp data dir, deterministic fallback encoder, freshly seeded DB."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="missinglink_test_")
os.environ["MISSINGLINK_DATA"] = _TMP
os.environ["MISSINGLINK_FORCE_FALLBACK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CASE = "MC-2026-0001"


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fresh(client):
    """Reset to the seeded synthetic scenario before a test."""
    from app.services import connectivity
    connectivity.set_simulated(None)
    r = client.post("/api/demo/reset")
    assert r.status_code == 200
    return client


def ids(result):
    return [c["record_id"] for c in result["candidates"]]
