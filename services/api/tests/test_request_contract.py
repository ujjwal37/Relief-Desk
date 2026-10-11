import json

from fastapi.testclient import TestClient

from app.agents.chat_intake import ChatIntakeAgent
from app.main import app
from app.tools.request_contract import canonical_request_json
from app.tools.storage import storage_service

client = TestClient(app)

HERO = "Gandhi school ke paas 5 log chat par hain, paani badh raha hai, 2 bache hain"
PIN = {"lat": 26.852, "lng": 80.925}
VOLATILE = {
    "id", "created_at", "updated_at", "report_ids", "merged_count", "merged_into", "cluster_id",
    "analysis", "analysis_status",
}


def _facts_from_card(card) -> dict:
    return {
        "incident_type": card.incident_type,
        "place_text": card.place_text,
        "people_count": card.people_count,
        "vulnerable": card.vulnerable,
        "hazard": card.hazard,
        "summary": card.summary,
    }


def test_chat_and_form_emit_byte_identical_request_json():
    agent = ChatIntakeAgent()
    chat = agent.process_turn(session_id="contract_chat", user_message=HERO, scenario_id="flood", lang_override="hinglish")
    assert chat.confirmation_card is not None
    facts = _facts_from_card(chat.confirmation_card)

    shared = dict(
        lang="hinglish",
        scenario_id="flood",
        lat=PIN["lat"],
        lng=PIN["lng"],
        **facts,
    )
    chat_json = canonical_request_json(**shared)
    # Form path: the coordinator-facing fields the user confirmed on the tile form.
    form_json = canonical_request_json(**shared)
    assert chat_json == form_json
    assert chat_json.encode("utf-8") == form_json.encode("utf-8")

    before = {req.id for req in storage_service.list_requests()}
    body = {
        "text": facts["summary"],
        "lang": "hinglish",
        "scenario_id": "flood",
        "location_pin": PIN,
        "structured": {
            "incident_type": facts["incident_type"],
            "place_text": facts["place_text"],
            "people_count": facts["people_count"],
            "vulnerable": facts["vulnerable"],
            "hazard": facts["hazard"],
            "summary": facts["summary"],
        },
    }
    chat_resp = client.post("/api/reports", json={**body, "channel": "text", "source_id": "contract_chat"})
    form_resp = client.post("/api/reports", json={**body, "channel": "form", "source_id": "contract_form"})
    assert chat_resp.status_code == 200
    assert form_resp.status_code == 200

    created = [req for req in storage_service.list_requests() if req.id not in before]
    assert len(created) == 2
    views = []
    for req in created:
        dumped = req.model_dump(mode="json")
        for key in VOLATILE:
            dumped.pop(key, None)
        views.append(json.dumps(dumped, sort_keys=True, separators=(",", ":")))
    assert views[0] == views[1]
