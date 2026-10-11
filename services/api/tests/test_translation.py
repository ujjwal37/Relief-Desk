import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tools.translation import translation_service, TranslationResult
from app.tools.storage import storage_service

client = TestClient(app)


def test_detect_language():
    # Hindi Devanagari
    assert translation_service.detect_language("शिव मंदिर के पास 4 लोग फंसे हैं") == "hi"
    assert translation_service.detect_language("पानी बढ़ रहा है") == "hi"

    # Tamil
    assert translation_service.detect_language("சிவன் கோவில் அருகே 4 பேர் சிக்கியுள்ளனர்") == "ta"
    assert translation_service.detect_language("வெள்ளத்தில் சிக்கியுள்ளோம்") == "ta"

    # Hinglish
    assert translation_service.detect_language("shiva temple ke paas paani badh raha hai jaldi bachao") == "hinglish"
    assert translation_service.detect_language("ghar me paani aa gaya hai") == "hinglish"

    # English
    assert translation_service.detect_language("Water entering first floor near Nedumudi Boat Jetty. Urgent boat needed.") == "en"
    assert translation_service.detect_language("Rescue required at Main Market") == "en"


def test_translate_report_hindi():
    text_hi = "वार्ड 7 में शिव मंदिर के पास 4 लोग फंसे हैं, पानी कमर तक आ गया है। नाव भेजिए।"
    res = translation_service.translate_report(text_hi)

    assert isinstance(res, TranslationResult)
    assert res.detected_language == "hi"
    assert "Shiva Temple" in res.text_en or "rescue" in res.text_en.lower()
    assert res.confidence >= 0.80
    assert not res.is_low_confidence
    assert "en" in res.translations
    assert "hi" in res.translations
    assert "ta" in res.translations


def test_translate_report_hinglish():
    text_hinglish = "clock tower ghanta ghar ke peeche paani badh raha hai, oxygen cylinder chahiye"
    res = translation_service.translate_report(text_hinglish)

    assert isinstance(res, TranslationResult)
    assert res.detected_language == "hinglish"
    assert "Clock Tower" in res.text_en or "oxygen" in res.text_en.lower()
    assert res.confidence >= 0.80
    assert not res.is_low_confidence


def test_translate_report_tamil():
    text_ta = "சிவன் கோவில் அருகே 4 பேர் சிக்கியுள்ளனர், தயவுசெய்து உடனடியாக படகு அனுப்பவும்."
    res = translation_service.translate_report(text_ta)

    assert isinstance(res, TranslationResult)
    assert res.detected_language == "ta"
    assert "Shiva Temple" in res.text_en or "rescue" in res.text_en.lower()
    assert res.confidence >= 0.80
    assert not res.is_low_confidence


def test_translation_caching():
    phrase = "gandhi school relief camp ration khatam"
    res1 = translation_service.translate_report(phrase)
    assert res1.confidence >= 0.80

    # Second call should be served from memory or disk cache
    res2 = translation_service.translate_report(phrase)
    assert res2.cached is True
    assert res2.text_en == res1.text_en


def test_low_confidence_flagging():
    # Input too short (< 5 chars) or repetitive punctuation
    short_input = "???"
    res_short = translation_service.translate_report(short_input)
    assert res_short.is_low_confidence is True
    assert res_short.confidence < 0.70

    gibberish = "aaaaa"
    res_gib = translation_service.translate_report(gibberish)
    assert res_gib.is_low_confidence is True
    assert res_gib.confidence < 0.70


def test_submit_report_integration_low_confidence():
    payload = {
        "text": "???",
        "scenario_id": "flood",
        "location_pin": {"lat": 26.85, "lng": 80.93},
    }
    resp = client.post("/api/reports", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "low_translation_confidence" in data["flags"]
    assert "needs_human_review" in data["flags"]

    # Verify stored request has low translation confidence
    req_id = data["request_id"]
    stored = storage_service.get_request(req_id)
    assert stored is not None
    assert stored.translation_confidence < 0.70
    assert "low_translation_confidence" in stored.flags
