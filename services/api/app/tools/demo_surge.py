"""A bounded, synthetic five-report replay through normal intake. Never dispatches."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from app.agents.pipeline import spawn
from app.tools.events import publish

logger = logging.getLogger("relief_desk.demo_surge")
_lock = threading.Lock()


@dataclass
class SurgeState:
    run_id: str = ""
    running: bool = False
    submitted: int = 0
    failed: int = 0
    started: float = 0.0
    report_ids: list[str] = field(default_factory=list)


_state = SurgeState()


def snapshot() -> dict:
    with _lock:
        return {"run_id": _state.run_id, "running": _state.running, "submitted": _state.submitted,
                "failed": _state.failed, "total": 5}


def start_surge(actor: str) -> dict:
    global _state
    with _lock:
        if _state.running:
            raise ValueError("A synthetic surge is already running")
        if _state.started and time.monotonic() - _state.started < 30:
            raise ValueError("Please wait before starting another synthetic surge")
        _state = SurgeState(run_id=uuid.uuid4().hex[:10], running=True, started=time.monotonic())
        run_id = _state.run_id
    accepted = snapshot()
    try:
        spawn(lambda: _run(run_id, actor))
    except Exception:
        with _lock:
            _state.running = False
        raise
    return accepted


def _run(run_id: str, actor: str) -> None:
    from app.api.reports import ReportSubmitRequest, submit_report
    from app.tools.storage import storage_service

    # Fictional people/streets. The first pair shares one precise synthetic rooftop.
    lines = [
        ("hi", "काल्पनिक रिपोर्ट। Chalakudy Cedar rooftop पर 4 लोग फंसे हैं। पानी बढ़ रहा है, नाव चाहिए।", 4, "rescue", 10.303, 76.335, "Chalakudy Cedar rooftop", {}),
        ("en", "Synthetic. Same Chalakudy Cedar rooftop: now 7 people including 2 elderly are stranded; water rising, need a boat.", 7, "rescue", 10.303, 76.335, "Chalakudy Cedar rooftop", {"elderly": True}),
        ("en", "Synthetic. 1 elderly disabled patient near St. Jude Varapuzha has oxygen running out. Medical transport needed, water rising.", 1, "medical", 10.07985, 76.27371, "St. Jude Varapuzha", {"elderly": True, "disabled": True, "medical_need": True}),
        ("en", "Synthetic. 12 people need food packets at Chalakudy Cedar relief camp, no evacuation needed.", 12, "food", 10.304, 76.336, "Chalakudy Cedar relief camp", {}),
        ("en", "Synthetic. 6 people need shelter at Chalakudy Cedar hall. Their home is submerged.", 6, "shelter", 10.305, 76.337, "Chalakudy Cedar hall", {}),
    ]
    try:
        storage_service.record_audit(actor=actor, action="demo_surge_started", target=run_id, after={"synthetic": True})
        for index, (lang, text, people, kind, lat, lng, place, vuln) in enumerate(lines):
            if index:
                time.sleep(2)
            try:
                result = submit_report(ReportSubmitRequest(
                    text=text, raw_text=text, lang=lang, source_id=f"surge-{run_id}-{index}",
                    idempotency_key=f"surge-{run_id}-{index}", location_pin={"lat": lat, "lng": lng},
                    structured={"incident_type": kind, "place_text": place, "people_count": people,
                                "vulnerable": vuln, "hazard": "water_rising" if index < 3 else "none"},
                ))
                with _lock:
                    _state.submitted += 1
                    _state.report_ids.append(result.report_id)
            except Exception:
                logger.exception("Synthetic surge report %s/%s failed", run_id, index)
                with _lock:
                    _state.failed += 1
            publish({"type": "demo.surge", **snapshot(), "request_ids": []})
    finally:
        with _lock:
            _state.running = False
        publish({"type": "demo.surge", **snapshot(), "request_ids": []})
