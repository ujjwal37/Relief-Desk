import json
from unittest.mock import MagicMock
import pytest

from app.agents.intake import PHOTO_INTAKE_PROMPT, IntakeAgent, intake_agent
from app.models.schemas import AiCall, IncidentType, HazardType


def test_photo_intake_prompt_no_prefilled_rescue_or_water_rising():
    # Assert the prompt no longer contains a pre-filled rescue / water_rising example
    assert '"type":"rescue"' not in PHOTO_INTAKE_PROMPT
    assert '"type": "rescue"' not in PHOTO_INTAKE_PROMPT
    assert '"hazard":"water_rising"' not in PHOTO_INTAKE_PROMPT
    assert '"hazard": "water_rising"' not in PHOTO_INTAKE_PROMPT

    # Neutral placeholders showing allowed choices should be present
    assert "one of other|rescue" in PHOTO_INTAKE_PROMPT
    assert "one of none|water_rising" in PHOTO_INTAKE_PROMPT

    # Plain instruction for non-emergency/unrelated photos should be present
    lower_prompt = PHOTO_INTAKE_PROMPT.lower()
    assert "a photo with no flood, injury, trapped people or damage" in lower_prompt
    assert "selfie, screenshot, document, meme" in lower_prompt
    assert "type other" in lower_prompt
    assert "hazard none" in lower_prompt
    assert "people count null" in lower_prompt


def test_parse_media_report_requests_at_least_512_tokens(monkeypatch):
    captured = {}
    fake_response = json.dumps({
        "type": "other",
        "people": {"count": None, "confidence": 0.0},
        "place_text": None,
        "hazard": "none",
        "vulnerable": {
            "child": False,
            "elderly": False,
            "disabled": False,
            "pregnant": False,
            "medical_need": False,
        },
        "notes": "screenshot without crisis",
        "text_en": "screenshot without crisis",
        "text_hi": "स्क्रीनशॉट",
        "language": "en",
        "urgency_hint": "low",
        "confidence": {
            "type": 1.0,
            "place": 1.0,
            "people": 1.0,
            "vulnerable": 1.0,
            "urgency": 1.0,
        },
        "secondary_needs": [],
        "is_update_phrase": False,
        "evidence_spans": {},
        "translation_confidence": 1.0,
        "original_text": "",
        "water_depth": "unknown",
        "water_depth_quote": None,
    })

    def fake_generate_media_content(*args, **kwargs):
        tokens = kwargs.get("max_output_tokens")
        if tokens is None and len(args) > 5:
            tokens = args[5]
        captured["max_output_tokens"] = tokens
        return fake_response

    monkeypatch.setattr(intake_agent.client, "generate_media_content", fake_generate_media_content)
    monkeypatch.setattr(intake_agent.client, "last_ai", AiCall(provider="gemini", model="gemini-2.5-flash"))

    result = intake_agent.parse_media_report(
        raw_text="",
        media=b"fake_image_bytes",
        mime_type="image/jpeg",
    )

    assert captured.get("max_output_tokens") is not None
    assert captured["max_output_tokens"] >= 512
    assert result.type == IncidentType.OTHER
    assert result.hazard == HazardType.NONE


def test_parse_media_report_mock_client_captures_argument():
    mock_client = MagicMock()
    fake_response = json.dumps({
        "type": "other",
        "people": {"count": None, "confidence": 0.0},
        "place_text": None,
        "hazard": "none",
        "vulnerable": {
            "child": False,
            "elderly": False,
            "disabled": False,
            "pregnant": False,
            "medical_need": False,
        },
        "notes": "meme",
        "text_en": "meme",
        "text_hi": "मीम",
        "language": "en",
        "urgency_hint": "low",
        "confidence": {
            "type": 1.0,
            "place": 1.0,
            "people": 1.0,
            "vulnerable": 1.0,
            "urgency": 1.0,
        },
        "secondary_needs": [],
        "is_update_phrase": False,
        "evidence_spans": {},
        "translation_confidence": 1.0,
        "original_text": "",
        "water_depth": "unknown",
        "water_depth_quote": None,
    })
    mock_client.generate_media_content.return_value = fake_response
    mock_client.last_ai = AiCall(provider="gemini", model="gemini-2.5-flash")

    agent = IntakeAgent(client=mock_client)
    res = agent.parse_media_report(
        raw_text="dashboard screenshot",
        media=b"image_content_bytes",
        mime_type="image/png",
    )

    assert mock_client.generate_media_content.called
    call_kwargs = mock_client.generate_media_content.call_args.kwargs
    call_args = mock_client.generate_media_content.call_args.args
    tokens = call_kwargs.get("max_output_tokens")
    if tokens is None and len(call_args) > 5:
        tokens = call_args[5]
    assert tokens is not None
    assert tokens >= 512
    assert res.type == IncidentType.OTHER
    assert res.hazard == HazardType.NONE
