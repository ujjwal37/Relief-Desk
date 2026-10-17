"""Ask the desk: rule fallback, Gemini function-call path, read-only endpoint."""
from app.agents import desk_query as dq
from app.models.firestore_models import RequestStatus, StoredRequest, VulnerableFlags


def _rows():
    return [
        StoredRequest(id="A", ward_id="ward_4", type="rescue", vulnerable=VulnerableFlags(elderly=True), urgency_score=9),
        StoredRequest(id="B", ward_id="ward_4", type="food", vulnerable=VulnerableFlags(elderly=True),
                      status=RequestStatus.DISPATCHED),
        StoredRequest(id="C", ward_id="ward_10", type="food", vulnerable=VulnerableFlags(child=True), people_count=6),
        StoredRequest(id="D", ward_id="ward_4", type="medical"),
    ]


def test_rules_english():
    f = dq.rule_filters("which elderly cases in Aluva are still waiting?")
    assert f["ward_ids"] == ["ward_4"] and f["vulnerable"] == ["elderly"] and f["waiting_only"]
    hits, total = dq.run_filters(_rows(), f)
    assert [h.id for h in hits] == ["A"] and total == 1


def test_rules_hinglish_and_hindi():
    f = dq.rule_filters("Wayanad mein bacche wale khana cases")
    assert set(f["ward_ids"]) == {"ward_10", "ward_11", "ward_12"}
    assert f["types"] == ["food"] and f["vulnerable"] == ["child"]
    assert [h.id for h in dq.run_filters(_rows(), f)[0]] == ["C"]
    h = dq.rule_filters("आलुवा में बुजुर्ग")
    assert h["ward_ids"] == ["ward_4"] and h["vulnerable"] == ["elderly"]


def test_rules_malayalam():
    f = dq.rule_filters("Aluva പ്രായമായ കാത്തിരിക്കുന്നു")
    assert f["vulnerable"] == ["elderly"] and f["waiting_only"]


def test_gemini_function_call_is_cleaned(monkeypatch):
    from app.llm import client as llm

    monkeypatch.setattr(llm.llm_client.guard, "failures", 0, raising=False)
    fake = lambda q, t: ({"types": ["food", "drop_table"], "ward_ids": ["ward_10", "ward_99"],
                          "waiting_only": True, "min_people": "5", "reason": "Food cases in Meppadi."}, 321)
    out = dq.ask("Meppadi food 5 people", _rows(), call=fake)
    assert out["ai"]["provider"] == "gemini" and out["ai"]["tokens"] == 321
    assert out["filters"]["types"] == ["food"] and out["filters"]["ward_ids"] == ["ward_10"]
    assert [c["id"] for c in out["cases"]] == ["C"] and out["reason"] == "Food cases in Meppadi."
    assert out["trace"][0]["provider"] == "gemini" and out["trace"][1]["provider"] == "tool"


def test_gemini_failure_falls_back_to_rules(monkeypatch):
    from app.llm import client as llm

    monkeypatch.setattr(llm.llm_client.guard, "failures", 0, raising=False)

    def boom(q, t):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    out = dq.ask("elderly in Aluva still waiting", _rows(), call=boom)
    assert out["ai"]["provider"] == "fallback" and out["ai"]["fallback_reason"] == "quota"
    assert [c["id"] for c in out["cases"]] == ["A"]
    monkeypatch.setattr(llm.llm_client.guard, "failures", 0, raising=False)


def test_endpoint_is_read_only():
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_coordinator, CoordinatorUser
    from app.main import app
    from app.tools.storage import storage_service

    app.dependency_overrides[get_current_coordinator] = lambda: CoordinatorUser(uid="t", role="coordinator", email="demo-coordinator@reliefdesk.internal")
    try:
        before = {k: v.model_dump_json() for k, v in storage_service._requests.items()}
        r = TestClient(app).post("/api/desk/ask", json={"question": "elderly cases in Aluva still waiting"})
        assert r.status_code == 200
        body = r.json()
        assert body["ai"]["provider"] == "fallback"
        assert all(c["ward_id"] == "ward_4" for c in body["cases"])
        assert {k: v.model_dump_json() for k, v in storage_service._requests.items()} == before
    finally:
        app.dependency_overrides.clear()


def test_critical_question_counts_only_critical_even_if_the_model_drops_the_band(monkeypatch):
    """QA r4: 'How many critical cases are waiting?' answered with every waiting case."""
    from app.llm import client as llm

    monkeypatch.setattr(llm.llm_client.guard, "failures", 0, raising=False)
    rows = [
        StoredRequest(id="K1", ward_id="ward_1", type="rescue", urgency_score=92),
        StoredRequest(id="K2", ward_id="ward_2", type="medical", urgency_score=85),
        StoredRequest(id="U1", ward_id="ward_2", type="food", urgency_score=65),
        StoredRequest(id="W1", ward_id="ward_3", type="food", urgency_score=30),
    ]
    fake = lambda q, t: ({"bands": [], "waiting_only": True, "reason": "Waiting cases."}, 50)
    out = dq.ask("How many critical cases are waiting?", rows, call=fake)
    assert out["filters"]["bands"] == ["critical"]
    assert sorted(c["id"] for c in out["cases"]) == ["K1", "K2"]
