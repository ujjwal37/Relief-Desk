import json
from types import SimpleNamespace

from app.agents.depth import band_of, depth_rank, validate_depth
from app.agents.intake import SYSTEM_INTAKE_PROMPT, ReportAnalysis

BOAT = SimpleNamespace(kind="boat")
VAN = SimpleNamespace(kind="medical")


def req(band):
    return SimpleNamespace(water_depth={"band": band, "quote": "x", "source": "gemini"} if band else None)


def test_prompt_asks_for_depth_with_quote():
    assert "water_depth" in SYSTEM_INTAKE_PROMPT and "water_depth_quote" in SYSTEM_INTAKE_PROMPT


def test_quote_must_be_in_report():
    raw = "Water is chest deep, 4 people on the terrace"
    assert validate_depth("chest", "chest deep", raw, "gemini")["band"] == "chest"
    assert validate_depth("chest", "up to the neck", raw, "gemini")["band"] == "unknown"
    assert validate_depth("bogus", "chest deep", raw, "gemini") is None
    assert validate_depth("unknown", None, raw, "gemini") is None


def test_deep_water_prefers_boat():
    assert depth_rank(req("chest"), BOAT) < depth_rank(req("chest"), VAN)
    assert depth_rank(req("roof"), BOAT) == 0


def test_shallow_water_prefers_ground_team():
    assert depth_rank(req("knee"), VAN) < depth_rank(req("knee"), BOAT)


def test_unknown_keeps_current_behaviour():
    assert depth_rank(req(None), BOAT) == depth_rank(req(None), VAN) == 0
    assert band_of(req(None)) == "unknown"


def test_mocked_gemini_reply_parses_depth():
    reply = {"type": "rescue", "secondary_needs": [], "place_text": "Aluva", "people": {"count": 3, "confidence": 0.9},
             "vulnerable": {"child": False, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
             "hazard": "water_rising", "urgency_hint": "critical", "language": "en", "is_update_phrase": False,
             "confidence": {"type": 0.9, "place": 0.8, "people": 0.9, "vulnerable": 0.8, "urgency": 0.9},
             "evidence_spans": {}, "notes": "", "text_en": "Water is waist deep", "text_hi": "",
             "translation_confidence": 0.9, "likely_hoax": False, "hoax_reason": None,
             "water_depth": "waist", "water_depth_quote": "waist deep"}
    parsed = ReportAnalysis.model_validate_json(json.dumps(reply))
    assert parsed.water_depth == "waist" and parsed.water_depth_quote == "waist deep"
    assert validate_depth(parsed.water_depth, parsed.water_depth_quote, "Water is waist deep at Aluva", "gemini")["band"] == "waist"
