from datetime import datetime, timedelta, timezone

from app.models.firestore_models import RequestStatus, StoredRequest
from app.models.schemas import HazardType, IncidentType, VulnerableFlags
from app.tools.scoring import scoring_engine


def test_same_case_scores_higher_after_two_hours():
    created = datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)
    req = StoredRequest(
        id="req_wait",
        type=IncidentType.RESCUE,
        place_text="Ward 7",
        people_count=3,
        vulnerable=VulnerableFlags(child=True),
        hazard=HazardType.WATER_RISING,
        status=RequestStatus.NEW,
        created_at=created.isoformat(),
    )
    early = scoring_engine.compute_urgency(req, now=created)
    later = scoring_engine.compute_urgency(req, now=created + timedelta(hours=2))
    assert later.score > early.score
    assert later.breakdown["wait_points"] > early.breakdown["wait_points"]
    assert later.breakdown["wait_minutes"] == 120
