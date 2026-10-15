import base64
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tools.storage import storage_service

client = TestClient(app)


def test_list_synthetic_voice_notes():
    """Verify catalog returns 8 synthetic voice notes across languages."""
    response = client.get("/api/voice/notes")
    assert response.status_code == 200
    notes = response.json()
    assert len(notes) >= 8
    # Verify languages represented
    langs = {n["lang"] for n in notes}
    assert langs == {"en", "hi"}
    # VN-01, the old rooftop TTS, and the Aluva medicine TTS used by the one-click voice sample.
    assert sum(1 for n in notes if n["lang"] == "hi") >= 2
    # All confidences > 0.80
    assert all(n["asr_confidence"] >= 0.80 for n in notes)


def test_hindi_voice_note_pipeline():
    """CRITICAL ACCEPTANCE CRITERIA:
    Hindi voice note -> transcript -> request; transcript stored."""
    response = client.post(
        "/api/reports",
        json={
            "channel": "voice",
            "voice_note_id": "VN-01",
            "source_id": "phone_mic_device_1",
            "lang": "hi",
            "scenario_id": "flood",
            "location_pin": {"lat": 26.852, "lng": 80.931}
        }
    )
    assert response.status_code == 200
    data = response.json()

    assert data["report_id"]
    assert data["request_id"]
    assert data["transcript"] is not None
    assert "महादेव मंदिर" in data["transcript"]
    assert "वार्ड 7" in data["transcript"]
    assert data["asr_confidence"] == 0.94

    # Verify StoredReport in persistence holds transcript and asr_confidence
    stored_rep = storage_service.get_report(data["report_id"])
    assert stored_rep is not None
    assert stored_rep.channel == "voice"
    assert stored_rep.transcript == data["transcript"]
    assert stored_rep.asr_confidence == 0.94

    # Verify extracted request
    stored_req = storage_service.get_request(data["request_id"])
    assert stored_req is not None
    assert stored_req.people_count == 4
    assert stored_req.vulnerable.child is True
    assert stored_req.vulnerable.elderly is True


def test_english_medical_voice_note_pipeline():
    """Verify the English medical voice note."""
    response = client.post(
        "/api/reports",
        json={
            "channel": "voice",
            "voice_note_id": "VN-02",
            "source_id": "phone_mic_device_2",
            "lang": "en",
            "scenario_id": "flood"
        }
    )
    assert response.status_code == 200
    data = response.json()

    assert "Aluva Bus Stand" in data["transcript"]
    assert data["asr_confidence"] == 0.91

    stored_req = storage_service.get_request(data["request_id"])
    assert stored_req is not None
    assert stored_req.vulnerable.medical_need is True


def test_base64_audio_submission():
    """Verify base64 audio payload triggers ASR transcription."""
    dummy_wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    b64 = base64.b64encode(dummy_wav_bytes).decode("ascii")

    response = client.post(
        "/api/reports",
        json={
            "channel": "voice",
            "audio_base64": b64,
            "source_id": "audio_recorder_app",
            "lang": "hi",
            "scenario_id": "flood"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] is not None
    assert data["asr_confidence"] >= 0.80
