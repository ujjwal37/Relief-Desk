"""SSE: one stream, the audit actions the desk cares about, and no buffering headers."""
import asyncio
import queue

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.events import SSE_HEADERS, _stream, _visible, events
from app.main import app
from app.tools.events import ACTION_KIND, emit_audit, publish, reset_for_tests, subscribe, unsubscribe

client = TestClient(app)
TOKEN = "demo-coordinator-token"


def setup_function():
    reset_for_tests()


def test_audit_actions_map_to_the_desk_events():
    assert ACTION_KIND["request_created"] == "case.created"
    assert ACTION_KIND["cluster_created"] == "case.merged"
    assert ACTION_KIND["request_saved"] == "case.updated"
    assert ACTION_KIND["status_change"] == "case.updated"
    assert ACTION_KIND["match_approved"] == "dispatch.created"
    assert ACTION_KIND["location_update"] == "team.updated"


def test_a_saved_case_is_published_to_subscribers():
    box = subscribe()
    try:
        emit_audit("request_created", "req_live", {"id": "req_live", "report_ids": ["rep_live"]})
        event = box.get(timeout=1)
    finally:
        unsubscribe(box)
    assert event["type"] == "case.created"
    assert event["request_id"] == "req_live"


def test_events_require_a_coordinator_or_status_token():
    missing = client.get("/api/events")
    assert missing.status_code == 401
    rejected = client.get("/api/events", params={"report_id": "missing", "status_token": "nope"})
    assert rejected.status_code == 401


def test_a_reporter_only_hears_their_own_case():
    own = {"type": "case.updated", "request_id": "req_a", "request_ids": ["req_a"]}
    assert _visible(own, None) is True
    assert _visible(own, "req_a") is True
    assert _visible(own, "req_b") is False
    assert _visible({"type": "heartbeat"}, "req_b") is True


def test_the_stream_flushes_a_case_event_without_buffering():
    # TestClient waits for a finished body, so an open stream is read here instead.
    text, media_type, buffering, cache = asyncio.run(_read_one_case_event())
    assert text.startswith("retry: 5000")
    assert "case.created" in text
    assert "req_stream" in text
    assert media_type == "text/event-stream"
    assert buffering == SSE_HEADERS["X-Accel-Buffering"]
    assert "no-cache" in cache


async def _read_one_case_event() -> tuple[str, str, str, str]:
    class Req:
        async def is_disconnected(self) -> bool:
            return False

    agen = _stream(Req(), None)
    out = [await agen.__anext__(), await agen.__anext__()]
    nxt = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0.05)
    publish({
        "type": "case.created",
        "id": "req_stream",
        "request_id": "req_stream",
        "request_ids": ["req_stream"],
    })
    out.append(await asyncio.wait_for(nxt, 2))
    await agen.aclose()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/events",
        "raw_path": b"/api/events",
        "query_string": b"token=demo-coordinator-token",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    response = await events(Request(scope), token=TOKEN, report_id=None, status_token=None)
    await response.body_iterator.aclose()
    return "".join(out), response.media_type, response.headers["x-accel-buffering"], response.headers["cache-control"]


def test_queue_timeout_is_the_heartbeat_wait():
    box = subscribe()
    try:
        raised = False
        try:
            box.get(timeout=0.01)
        except queue.Empty:
            raised = True
        assert raised
    finally:
        unsubscribe(box)
