import time

from app.agents import sitrep


def test_fast_returns_rules_summary_without_waiting(monkeypatch):
    sitrep._cache.clear()
    started = []
    monkeypatch.setattr(sitrep, "_warm_in_background", lambda: started.append(1))
    t0 = time.monotonic()
    res = sitrep.generate_sitrep_fast()
    assert time.monotonic() - t0 < 2
    assert res.ai.provider == "fallback"
    assert res.ai.fallback_reason == "sitrep_warming"
    assert str(res.counts.pending) in res.brief
    assert res.send is False
