"""One Server-Sent Events stream for the desk and for a reporter's own case."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.auth import verify_coordinator_token
from app.tools.events import HEARTBEAT_SECONDS, subscribe_async, unsubscribe
from app.tools.storage import storage_service

router = APIRouter(prefix="/api", tags=["Events"])

# Cloud Run and the dev proxy must not buffer this response.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "Content-Encoding": "identity",
}


def _case_for_report(report_id: str, status_token: str) -> str:
    report = storage_service.get_report(report_id)
    if report is None or not status_token or report.status_token != status_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return report.case_id or report.request_id or ""


def _live_case(case_id: Optional[str]) -> Optional[str]:
    """A report merged after the phone connected still hears the case it joined."""
    if not case_id:
        return case_id
    req = storage_service.get_request(case_id)
    if req is not None and req.merged_into:
        return req.merged_into
    return case_id


def _visible(event: dict, case_id: Optional[str]) -> bool:
    if case_id is None:
        return True
    if event.get("type") == "heartbeat":
        return True
    ids = {str(item) for item in (event.get("request_ids") or []) if item}
    if event.get("request_id"):
        ids.add(str(event["request_id"]))
    return bool(case_id) and case_id in ids


def _frame(event: dict) -> str:
    payload = json.dumps(event, separators=(",", ":"))
    return f"event: {event['type']}\ndata: {payload}\n\n"


async def _stream(request: Request, case_id: Optional[str]) -> AsyncIterator[str]:
    box = subscribe_async()
    try:
        # Ask the browser to wait 5s if it reconnects on its own. We also reconnect with backoff.
        yield "retry: 5000\n\n"
        yield ": connected\n\n"
        loop = asyncio.get_running_loop()
        last_sent = loop.time()
        while True:
            if await request.is_disconnected():
                break
            try:
                item = await box.get(HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield "event: heartbeat\ndata: {}\n\n"
                last_sent = loop.time()
                continue
            if _visible(item, case_id) or _visible(item, _live_case(case_id)):
                yield _frame(item)
                last_sent = loop.time()
            elif loop.time() - last_sent >= HEARTBEAT_SECONDS:
                # A busy desk sends other cases' events; this stream still needs bytes to stay open.
                yield "event: heartbeat\ndata: {}\n\n"
                last_sent = loop.time()
    finally:
        unsubscribe(box)


@router.get("/events")
async def events(
    request: Request,
    token: Optional[str] = Query(None),
    report_id: Optional[str] = Query(None),
    status_token: Optional[str] = Query(None),
):
    """Coordinator token sees every event. A status token sees that one case."""
    case_id: Optional[str] = None
    if report_id:
        case_id = _case_for_report(report_id, status_token or "")
    elif token:
        verify_coordinator_token(token)
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return StreamingResponse(
        _stream(request, case_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
