"""Embedding retrieval stays in the district. The judge says duplicate, update, or distinct."""
import json
import uuid

from fastapi.testclient import TestClient

from app.agents.dedupe import dedupe_agent
from app.agents.intake import intake_agent
from app.llm.embeddings import cosine, embed_texts, l2_normalize
from app.main import app
from app.models.firestore_models import IncidentType, RequestStatus, StoredRequest
from app.models.schemas import DedupeDecisionType, HazardType
from app.tools.storage import storage_service

client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-coordinator-token"}


def _unit():
    return l2_normalize([1.0] * 768)


def test_embedding_retrieval_keeps_the_same_district(monkeypatch):
    monkeypatch.setattr(dedupe_agent, "embedder", lambda texts: [_unit() for _ in texts])
    local = StoredRequest(
        id="req_local",
        type=IncidentType.RESCUE,
        place_text="Champakulam School",
        raw_text="4 log chhat par hain",
        ward_id="ward_2",
        lat=9.416,
        lng=76.411,
        people_count=4,
        hazard=HazardType.STRANDED,
        status=RequestStatus.NEW,
    )
    other_district = StoredRequest(
        id="req_aluva",
        type=IncidentType.RESCUE,
        place_text="Champakulam School",
        raw_text="4 log chhat par hain",
        ward_id="ward_4",
        lat=10.108,
        lng=76.353,
        people_count=4,
        status=RequestStatus.NEW,
    )
    extracted = intake_agent.parse_report("Champakulam School ke paas 4 log chhat par hain, boat bhejo")
    found = dedupe_agent.prefilter_candidates(
        new_req=extracted,
        new_lat=9.416,
        new_lng=76.411,
        new_ward="ward_2",
        existing_requests=[other_district, local],
    )
    assert [row.id for row in found] == ["req_local"]
    assert dedupe_agent._embed_scores["req_local"] == 1.0


def test_judge_returns_duplicate_update_or_distinct():
    extracted = intake_agent.parse_report("4 log")
    duplicate = dedupe_agent._decision_from_judge(
        json.dumps({
            "relation": "duplicate",
            "target_request_id": "req_local",
            "evidence": ["same church road and 4 people"],
        }),
        extracted,
    )
    update = dedupe_agent._decision_from_judge(
        json.dumps({"relation": "update", "target_request_id": "req_local", "evidence": ["now 6 people"]}),
        extracted,
    )
    distinct = dedupe_agent._decision_from_judge(
        json.dumps({"relation": "distinct", "target_request_id": None, "evidence": ["different street"]}),
        extracted,
    )
    assert duplicate.decision == DedupeDecisionType.DUPLICATE
    assert "4 people" in duplicate.evidence[0]
    assert update.decision == DedupeDecisionType.UPDATE
    assert update.changed_fields
    assert distinct.decision == DedupeDecisionType.NEW
    assert distinct.target_request_id is None


def test_live_judge_uses_the_embedding_candidate(monkeypatch):
    monkeypatch.setattr(dedupe_agent.client, "gemini_live", lambda: True)

    def generate_content(system_instruction, user_prompt, **kwargs):
        assert "duplicate" in user_prompt
        return json.dumps({
            "relation": "duplicate",
            "target_request_id": "req_local",
            "evidence": ["reworded Hinglish, same people"],
        })

    monkeypatch.setattr(dedupe_agent.client, "generate_content", generate_content)
    extracted = intake_agent.parse_report("Church Road par 4 log fas gaye")
    candidate = StoredRequest(
        id="req_local",
        type=IncidentType.RESCUE,
        place_text="Church Road",
        people_count=4,
        ward_id="ward_2",
    )
    dedupe_agent._embed_scores = {"req_local": 0.91}
    decision = dedupe_agent.evaluate("Church Road par 4 log fas gaye", extracted, [candidate])
    assert decision.decision == DedupeDecisionType.DUPLICATE
    assert any("gemini-embedding-001" in line for line in decision.evidence)


def test_missing_embeddings_fall_back_to_lexical_match(monkeypatch):
    monkeypatch.setattr(dedupe_agent, "embedder", lambda texts: None)
    existing = StoredRequest(
        id="req_lex",
        type=IncidentType.RESCUE,
        place_text="Mithra Church Road",
        raw_text="Mithra Church Road pe 4 log chhat par hain",
        ward_id="ward_2",
        lat=9.45,
        lng=76.39,
        people_count=4,
    )
    text = "Mithra Church Road par 4 log fas gaye, madad chahiye"
    extracted = intake_agent.parse_report(text)
    found = dedupe_agent.prefilter_candidates(extracted, 9.45, 76.39, "ward_2", [existing])
    assert [row.id for row in found] == ["req_lex"]
    decision = dedupe_agent.evaluate(text, extracted, found)
    assert decision.decision == DedupeDecisionType.DUPLICATE
    assert not any("gemini-embedding-001" in line for line in decision.evidence)


def test_embed_helper_returns_none_without_a_key():
    assert embed_texts(["boat at the jetty"]) is None
    assert abs(cosine(_unit(), _unit()) - 1.0) < 1e-9


def test_antigravity_skips_embeddings_and_uses_the_lexical_check(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "LLM_PROVIDER", "antigravity", raising=False)
    monkeypatch.setattr(dedupe_agent.client, "gemini_live", lambda: True)

    def boom(*_args, **_kwargs):
        raise AssertionError("Gemini was called")

    monkeypatch.setattr(dedupe_agent.client, "generate_content", boom)
    assert embed_texts(["boat at the jetty"]) is None
    existing = StoredRequest(
        id="req_lex",
        type=IncidentType.RESCUE,
        place_text="Mithra Church Road",
        raw_text="Mithra Church Road pe 4 log chhat par hain",
        ward_id="ward_2",
        lat=9.45,
        lng=76.39,
        people_count=4,
    )
    text = "Mithra Church Road par 4 log fas gaye, madad chahiye"
    extracted = intake_agent.parse_report(text)
    found = dedupe_agent.prefilter_candidates(extracted, 9.45, 76.39, "ward_2", [existing])
    assert [row.id for row in found] == ["req_lex"]
    decision = dedupe_agent.evaluate(text, extracted, found)
    assert decision.decision == DedupeDecisionType.DUPLICATE
    assert not any("gemini-embedding-001" in line for line in decision.evidence)


def test_merge_and_undo_are_audited():
    token = f"Mithralane{uuid.uuid4().hex[:6]}"
    pin = {"lat": 8.5, "lng": 76.9}
    first = client.post(
        "/api/reports",
        json={
            "text": f"{token} pe 4 log chhat par hain, boat bhejo",
            "lang": "hinglish",
            "channel": "text",
            "location_pin": pin,
            "idempotency_key": f"emb-a-{token}",
        },
    )
    second = client.post(
        "/api/reports",
        json={
            "text": f"{token} par 4 log fas gaye, madad chahiye",
            "lang": "hinglish",
            "channel": "text",
            "location_pin": pin,
            "idempotency_key": f"emb-b-{token}",
        },
    )
    assert second.json()["dedupe_decision"] == "duplicate"
    listed = client.get("/api/requests", headers=AUTH)
    cards = [row for row in listed.json() if token.lower() in (row.get("raw_text") or "").lower()]
    # Flagged, not merged. A person then clicks Merge.
    assert len(cards) == 2 and all(not c.get("merged_into") for c in cards)
    flagged = next(c for c in cards if (c.get("possible_duplicate") or {}).get("target_id"))
    primary_id = flagged["possible_duplicate"]["target_id"]
    merged = client.post(f"/api/requests/{primary_id}/merge", headers=AUTH,
                         json={"secondary_request_id": flagged["id"], "evidence": ["Coordinator merge"], "merged_by": "coordinator"})
    assert merged.status_code == 200, merged.text
    listed = client.get("/api/requests", headers=AUTH)
    cards = [row for row in listed.json() if token.lower() in (row.get("raw_text") or "").lower() and not row.get("merged_into")]
    assert len(cards) == 1
    assert cards[0]["merged_count"] == 2
    cluster_id = cards[0]["cluster_id"]
    created = storage_service.get_audit_trail(target=cluster_id)
    assert any(entry.action == "cluster_created" for entry in created)

    undone = client.post(f"/api/requests/{cards[0]['id']}/split", headers=AUTH)
    assert undone.status_code == 200, undone.text
    assert undone.json()["undone"] is True
    split_trail = storage_service.get_audit_trail(target=cluster_id)
    assert any(entry.action == "cluster_split" for entry in split_trail)
    again = client.get("/api/requests", headers=AUTH)
    restored = [row for row in again.json() if token.lower() in (row.get("raw_text") or "").lower()]
    assert len(restored) == 2
    assert all(row.get("merged_into") in (None, "") for row in restored)
