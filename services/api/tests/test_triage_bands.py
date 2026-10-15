"""Seeded flood cases must include several that the desk labels Needs help now."""
from app.tools.storage import storage_service

NOW = 80.0
SOON = 60.0


def test_seed_has_at_least_three_needs_help_now():
    storage_service.load_seed_incidents()
    rows = storage_service.list_requests()
    now = [row for row in rows if row.urgency_score >= NOW]
    assert len(now) >= 3
    reasons = " ".join((row.place_text or "") + " " + (row.raw_text or "") for row in now).lower()
    assert "oxygen" in reasons or "labor" in reasons or "pregnant" in reasons
    # The same threshold the chips and the briefing use: Immediate >= 80.
    assert all(row.urgency_score >= NOW for row in now)
    assert sum(1 for row in rows if SOON <= row.urgency_score < NOW) >= 1
