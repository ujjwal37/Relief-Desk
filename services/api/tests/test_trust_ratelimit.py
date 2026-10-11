from datetime import datetime, timezone, timedelta
from app.tools.ratelimit import RateLimiter
from app.tools.trust import (
    score_source_trust,
    evaluate_stale_status,
    detect_hoax_or_flood,
    detect_conflict_in_cluster,
)
from app.tools.storage import StorageService
from app.models.firestore_models import StoredRequest, RequestStatus
from app.models.schemas import HazardType


def test_burst_of_20_copies_flagged_rate_limited_and_nothing_deleted():
    storage = StorageService()
    limiter = RateLimiter(max_per_hour=10)
    source_id = "spammer_device_123"

    saved_reports = []
    # Send a burst of 20 copies from one source
    for i in range(20):
        is_limited, count = limiter.check_and_record(source_id)
        flags = ["rate_limited"] if is_limited else []
        report = storage.save_report_raw(
            raw_text="Copy paste emergency message text",
            source_id=source_id,
            flags=flags
        )
        saved_reports.append(report)

    # Acceptance criteria:
    # 1. Burst of 20 copies has reports flagged rate_limited
    rate_limited_reports = [r for r in saved_reports if "rate_limited" in r.flags]
    assert len(rate_limited_reports) == 10  # First 10 allowed, subsequent 10 flagged

    # 2. Nothing deleted: all 20 reports are stored in storage!
    assert len(storage.list_reports()) == 20
    for r in saved_reports:
        assert storage.get_report(r.id) is not None


def test_stale_request_becomes_needs_recheck_and_not_deleted():
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(minutes=150)).isoformat()

    req = StoredRequest(
        id="req_stale_1",
        updated_at=old_time,
        status=RequestStatus.NEW
    )

    is_stale = evaluate_stale_status(req, stale_threshold_minutes=120, current_time=now)
    assert is_stale is True
    assert "stale" in req.flags
    assert req.status == RequestStatus.NEEDS_RECHECK


def test_hoax_and_conflict_flagging():
    # Hoax detection on viral message
    hoax_flags = detect_hoax_or_flood(
        existing_reports=[],
        new_raw_text="Forward this to 10 groups for free helicopter rescue",
        source_id="src_1"
    )
    assert "hoax" in hoax_flags

    # Conflict detection in cluster
    req1 = StoredRequest(id="r1", hazard=HazardType.WATER_RISING)
    req2 = StoredRequest(id="r2", hazard=HazardType.NONE)
    has_conflict = detect_conflict_in_cluster([req1, req2])
    assert has_conflict is True
    assert "conflict" in req1.flags
    assert "conflict" in req2.flags
