"""One shared live demo: eight synthetic reports through the normal intake pipeline.

A second start joins the run already in progress. Progress counts come from the
cases the pipeline actually saved. The pacer, not a sleep, spaces Gemini calls.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.agents.pipeline import wait_for_idle
from app.tools.events import publish

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_state: Dict[str, Any] = {
    "running": False,
    "status": "idle",
    "received": 0,
    "total": 8,
    "joined": 0,
    "flagged": 0,
    "critical": 0,
    "queue_position": 0,
    "active_id": None,
    "critical_id": None,
    "hoax_id": None,
    "primary_id": None,
    "case_ids": [],
    "error": None,
}


def samples_path() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "data" / "synthetic" / "live_samples.json"
        if candidate.is_file():
            return candidate
    return Path("data/synthetic/live_samples.json")


def load_samples() -> List[Dict[str, Any]]:
    payload = json.loads(samples_path().read_text(encoding="utf-8"))
    rows = payload.get("samples") or []
    if len(rows) != 8:
        raise RuntimeError(f"live demo expects 8 samples, found {len(rows)}")
    return rows


def snapshot() -> Dict[str, Any]:
    with _lock:
        return dict(_state)


def _publish(extra: Optional[Dict[str, Any]] = None) -> None:
    body = {"type": "demo.progress", **snapshot()}
    if extra:
        body.update(extra)
    publish(body)


def _set(**fields: Any) -> None:
    with _lock:
        _state.update(fields)
    _publish()


def _apply_case(request_id: str, sample_id: str) -> None:
    from app.tools.storage import storage_service

    req = storage_service.get_request(request_id)
    if req is None:
        return
    visible = storage_service.get_request(req.merged_into) if req.merged_into else req
    target = visible or req
    with _lock:
        ids = list(_state["case_ids"])
        if request_id not in ids:
            ids.append(request_id)
        joined = 0
        flagged = 0
        critical = 0
        critical_id = _state.get("critical_id")
        hoax_id = _state.get("hoax_id")
        primary_id = _state.get("primary_id")
        best = -1.0
        for cid in ids:
            row = storage_service.get_request(cid)
            if row is None:
                continue
            if row.merged_into:
                joined += 1
                row = storage_service.get_request(row.merged_into) or row
            flags = row.flags or []
            if any(flag in flags for flag in ("hoax", "likely_hoax", "hoax_or_flood")):
                flagged += 1
                hoax_id = row.id
            if (row.urgency_score or 0) >= 80 and not row.merged_into:
                critical += 1
                if (row.urgency_score or 0) >= best:
                    best = row.urgency_score or 0
                    critical_id = row.id
        if sample_id == "S1" and not req.merged_into:
            primary_id = req.id
        elif sample_id == "S1" and req.merged_into:
            primary_id = req.merged_into
        _state.update({
            "case_ids": ids,
            "joined": joined,
            "flagged": flagged,
            "critical": critical,
            "critical_id": critical_id,
            "hoax_id": hoax_id,
            "primary_id": primary_id,
            "active_id": target.id,
        })
    _publish()


def _run(submit: Callable[[Dict[str, Any]], Any]) -> None:
    try:
        rows = load_samples()
        _set(total=len(rows), status="running", running=True, error=None)
        for index, sample in enumerate(rows, start=1):
            from app.llm.pacer import gemini_pacer
            waiting = gemini_pacer.waiting
            _set(received=index - 1, status="waiting" if waiting else "running", queue_position=waiting)
            result = submit(sample)
            wait_for_idle(timeout=180)
            request_id = getattr(result, "request_id", None) or (result.get("request_id") if isinstance(result, dict) else None)
            if request_id:
                _apply_case(str(request_id), str(sample.get("id") or ""))
            _set(received=index, status="running", queue_position=0)
        final = snapshot()
        _set(running=False, status="done", queue_position=0, active_id=final.get("critical_id") or final.get("active_id"))
    except Exception as exc:
        _set(running=False, status="error", error=str(exc)[:240])


def start(submit: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
    """Start the shared run, or return the run already going."""
    global _thread
    with _lock:
        if _state["running"] and _thread is not None and _thread.is_alive():
            return dict(_state)
        _state.update({
            "running": True,
            "status": "running",
            "received": 0,
            "joined": 0,
            "flagged": 0,
            "critical": 0,
            "queue_position": 0,
            "active_id": None,
            "critical_id": None,
            "hoax_id": None,
            "primary_id": None,
            "case_ids": [],
            "error": None,
        })
        _thread = threading.Thread(target=_run, args=(submit,), name="live-demo", daemon=True)
        _thread.start()
        return dict(_state)


def reset_for_tests() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=5)
    with _lock:
        _thread = None
        _state.update({
            "running": False,
            "status": "idle",
            "received": 0,
            "joined": 0,
            "flagged": 0,
            "critical": 0,
            "queue_position": 0,
            "active_id": None,
            "critical_id": None,
            "hoax_id": None,
            "primary_id": None,
            "case_ids": [],
            "error": None,
        })
