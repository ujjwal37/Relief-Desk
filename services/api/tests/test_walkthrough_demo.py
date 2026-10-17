from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.firestore_models import StoredRequest, StoredResource
from app.agents.matching import matching_agent
from app.tools import demo_surge
from app.tools.storage import storage_service
from app.tools.events import subscribe, unsubscribe

client = TestClient(app)
AUTH = {'Authorization': 'Bearer demo-coordinator-token'}


def test_demo_login_is_forbidden_when_demo_mode_is_off(monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    response = client.post('/api/auth/demo-login')
    assert response.status_code == 403
    assert 'off' in response.json()['detail'].lower()


def test_surge_is_authenticated_and_demo_only(monkeypatch):
    assert client.post('/api/demo/simulate-surge').status_code == 401
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    assert client.post('/api/demo/simulate-surge', headers=AUTH).status_code == 403


def test_surge_submits_five_spaced_reports_with_real_updates_and_no_dispatch(monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', True)
    monkeypatch.setattr(settings, 'AI_MODE', 'fallback')
    monkeypatch.setattr(demo_surge, '_state', demo_surge.SurgeState())
    held = []
    monkeypatch.setattr(demo_surge, 'spawn', lambda job: held.append(job))
    sleeps = []
    monkeypatch.setattr(demo_surge.time, 'sleep', lambda seconds: sleeps.append(seconds))
    storage_service.reset_demo()
    box = subscribe()
    try:
        response = client.post('/api/demo/simulate-surge', headers=AUTH)
        assert response.status_code == 202
        assert client.post('/api/demo/simulate-surge', headers=AUTH).status_code == 409
        held[0]()
        state = client.get('/api/demo/surge', headers=AUTH).json()
        assert state['submitted'] == 5 and state['failed'] == 0 and not state['running']
        assert sleeps == [2, 2, 2, 2]
        reports = [r for r in storage_service.list_reports() if r.source_id.startswith('surge-')]
        assert len(reports) == 5
        requests = storage_service.list_requests()
        assert all(r.status.value != 'dispatched' for r in requests)
        assert any(r.people_count == 7 for r in requests)
        alerts = client.get('/api/alerts', headers=AUTH).json()
        assert any(r['kind'] == 'spike' for r in alerts)
        events = []
        while not box.empty(): events.append(box.get_nowait()['type'])
        assert 'case.created' in events and 'demo.surge' in events
    finally:
        unsubscribe(box)
        storage_service.load_full_scenario()


def test_referral_stock_excludes_closer_clinic_and_is_not_restored_as_team_capacity():
    storage_service.load_full_scenario()
    req = storage_service.get_request('DOG-001')
    assert req.required_supplies == {'rig': 1}
    proposals = matching_agent.find_matches(req)
    assert proposals and proposals[0].resource_id == 'DOG-MED-02'
    assert all(p.resource_id != 'DOG-MED-01' for p in proposals)
    assert 'RIG: 3 in stock' in proposals[0].explanation
    team = storage_service.get_resource('DOG-MED-02')
    capacity = team.capacity_remaining
    try:
        match = storage_service.approve_match(proposals[0].match_id)
        storage_service.approve_match(match.id)  # retry
        assert team.supplies['rig'] == 2
        assert team.capacity_remaining == capacity - 1
        storage_service.mark_arrived(req.id)
        storage_service.complete_request(req.id)
        assert team.capacity_remaining == capacity
        assert team.supplies['rig'] == 2  # Supplies were allocated, not magically replenished.
    finally:
        storage_service.load_full_scenario()


def test_approval_rechecks_stock_under_contention():
    team = StoredResource(id='stock-race', kind='medical', name='Synthetic stock team', ward_id='ward_2',
                          lat=9.42, lng=76.41, capacity_total=8, capacity_remaining=8, supplies={'rig': 1})
    storage_service.save_resource(team)
    reqs = [StoredRequest(id=f'stock-race-{i}', type='animal_attack', lat=9.42, lng=76.41,
                          required_supplies={'rig': 1}, people_count=1) for i in range(2)]
    matches = []
    for req in reqs:
        storage_service.save_request(req)
        matches.append(next(p for p in matching_agent.find_matches(req, top_n=20) if p.resource_id == team.id))
    def approve(match):
        try:
            storage_service.approve_match(match.match_id)
            return True
        except ValueError:
            return False
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(approve, matches))
        assert outcomes.count(True) == 1
        assert team.supplies['rig'] == 0 and team.capacity_remaining == 7
    finally:
        storage_service.load_full_scenario()


def test_scenario_switch_preserves_used_inventory(monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', True)
    team = storage_service.get_resource('DOG-MED-02')
    team.supplies['rig'] = 1
    assert client.post('/api/demo/scenario/dog_attack', headers=AUTH).status_code == 200
    assert storage_service.get_resource(team.id).supplies['rig'] == 1
    assert client.post('/api/demo/scenario/unknown', headers=AUTH).status_code == 404
    storage_service.load_full_scenario()
