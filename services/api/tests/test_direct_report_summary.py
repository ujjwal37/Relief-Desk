"""A direct (non-chat) report gets a short summary in the reporter's language, not its own transcript."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_direct_malayalam_report_gets_a_short_summary_not_the_transcript():
    text = "ചമ്പക്കുളം പള്ളിക്ക് സമീപം 4 പേർ വീടിന്റെ മുകളിൽ കുടുങ്ങി, വെള്ളം ഉയരുന്നു, ബോട്ട് വേണം"
    res = client.post("/api/reports", json={"text": text, "lang": "ml", "location_pin": {"lat": 9.418, "lng": 76.409},
                                             "structured": {"incident_type": "rescue", "people_count": 4, "place_text": "Champakulam church"}})
    assert res.status_code in (200, 201), res.text
    summary = res.json()["summary"]
    assert summary and summary != text
    assert "4" in summary
    assert len(summary) < len(text)


def test_direct_english_report_summary_is_short():
    text = "Synthetic. 3 people stuck on the roof near Nedumudi temple, water rising fast, please send a boat quickly"
    res = client.post("/api/reports", json={"text": text, "location_pin": {"lat": 9.428, "lng": 76.394},
                                             "structured": {"incident_type": "rescue", "people_count": 3, "place_text": "Nedumudi temple"}})
    summary = res.json()["summary"]
    assert summary != text and "3" in summary and "Nedumudi" in summary
