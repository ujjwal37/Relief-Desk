import json
from types import SimpleNamespace

from app.agents import pipeline, review
from app.config import settings
from app.llm.adk_runtime import run_text_agent
from app.llm.client import llm_client
from app.models.firestore_models import StoredRequest, RequestStatus
from app.tools.storage import storage_service


def test_adk_runner_invokes_transport_and_returns_its_output():
    called = []
    def transport():
        called.append(True)
        return '{"text":"supplied facts only"}'
    result = run_text_agent('Intake', 'test-model', 'JSON {literal braces}', 'synthetic report', transport)
    assert json.loads(result)['text'] == 'supplied facts only'
    assert called == [True]


def test_review_rejects_invented_numbers(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'GEMINI_API_KEY', 'mock-key')
    monkeypatch.setattr(settings, 'AI_MODE', 'auto')
    monkeypatch.setattr('app.llm.client.CACHE_DIR', tmp_path)
    monkeypatch.setattr(llm_client.guard, 'circuit_open', lambda: False)
    monkeypatch.setattr(llm_client, '_call_gemini', lambda *args: '{"text":"Urgency is 9999"}')
    result = review.language_review('Triage', {'score': 72}, 'Tool score is 72')
    assert result['provider'] == 'fallback'
    assert result['text'] == 'Tool score is 72'
    assert result['fallback_reason'] == 'invalid_json'


def test_analysis_cannot_undo_a_coordinator_status_change(monkeypatch):
    req = StoredRequest(id='review-race', type='rescue', people_count=4, raw_text='synthetic four people', lat=9.47, lng=76.39)
    storage_service.save_request(req)
    def fake_review(agent, context, fallback):
        current = storage_service.get_request(req.id)
        current.status = RequestStatus.DISPATCHED
        current.assigned_resource_id = 'human-selected'
        current.reserved_people = 4
        return {'text': fallback, 'provider': 'tool', 'model': None, 'latency_ms': 1}
    monkeypatch.setattr(review, 'language_review', fake_review)
    pipeline.finish(req.id)
    done = storage_service.get_request(req.id)
    assert done.status == 'dispatched'
    assert done.assigned_resource_id == 'human-selected'
    assert done.reserved_people == 4
    assert done.analysis_status == 'complete'
    assert done.analysis['matching']['dispatched'] is False
    storage_service._requests.pop(req.id)
