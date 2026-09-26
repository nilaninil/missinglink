"""Connectivity detection (TCP to 1.1.1.1:53, cached 10 s) with a simulated override."""
import socket
import time

_state = {"simulated_offline": None, "checked_at": 0.0, "online": False}


def _probe():
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=1):
            return True
    except Exception:
        return False


def is_online() -> bool:
    if _state["simulated_offline"] is not None:
        return not _state["simulated_offline"]
    now = time.time()
    if now - _state["checked_at"] > 10:
        _state["online"] = _probe()
        _state["checked_at"] = now
    return _state["online"]


def set_simulated(offline):
    _state["simulated_offline"] = offline


def is_simulated():
    return _state["simulated_offline"] is not None


def status():
    return {"mode": "online" if is_online() else "offline", "simulated": is_simulated()}


def sync_status_for_new_rows():
    return "synced" if is_online() else "pending_sync"
