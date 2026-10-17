from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tools.storage import simulate_demo_checkins


def _team(i, mins_ago, synthetic=True):
    now = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)
    return SimpleNamespace(id=f"res_{i}", synthetic=synthetic, simulated=False,
                           location_updated_at=(now - timedelta(minutes=mins_ago)).isoformat())


def test_stale_synthetic_teams_get_recent_simulated_checkin():
    now = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)
    teams = [_team(i, 400) for i in range(20)]
    simulate_demo_checkins(teams, now)
    fresh = [t for t in teams if t.simulated]
    assert 0 < len(fresh) < 20  # some left stale on purpose
    for t in fresh:
        age = now - datetime.fromisoformat(t.location_updated_at)
        assert timedelta(minutes=2) <= age <= timedelta(minutes=26)


def test_real_and_recent_teams_untouched():
    now = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)
    real = _team(1, 400, synthetic=False)
    recent = _team(2, 10)
    before = recent.location_updated_at
    simulate_demo_checkins([real, recent], now)
    assert not real.simulated and not recent.simulated
    assert recent.location_updated_at == before
