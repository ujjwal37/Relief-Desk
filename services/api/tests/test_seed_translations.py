"""Hindi and Tamil seed lines must name the same place as the English line."""
import re
from pathlib import Path

import yaml

SEEDS = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"

# Tamil sentences use these names for the landmark the English line names.
TA_PLACE = {
    "Nedumudi Boat Jetty": "நெடுமுடி படகுத்துறை",
    "Kainakary LP School": "கைனகரி தொடக்கப்பள்ளி",
    "Champakulam School": "சம்பாக்குளம் பள்ளி",
    "Nedumudi Bridge": "நெடுமுடி பாலம்",
    "Mala School": "மாலா பள்ளி",
    "Champakulam Market": "சம்பாக்குளம் சந்தை",
    "Anthikad Bridge": "அந்திக்கட்டு பாலம்",
    "Puthumala": "புதுமலை",
    "Varapuzha School": "வரப்புழா பள்ளி",
    "Kalpetta School": "கல்பற்ற பள்ளி",
    "Mala Health Centre": "மாலா ஆரம்ப சுகாதார நிலையம்",
    "Anthikad School": "அந்திக்கட்டு பள்ளி",
    "Nedumudi School": "நெடுமுடி பள்ளி",
    "Vythiri Bridge": "வைத்திரி பாலம்",
    "Meppadi Relief Camp": "மேப்பாடி நிவாரண முகாம்",
    "Anthikad Relief Camp": "அந்திக்கட்டு நிவாரண முகாம்",
    "Kainakary Church": "கைனகரி தேவாலயம்",
    "Kalpetta Shelter": "கல்பற்ற தங்குமிடம்",
    "Nedumudi Relief Camp": "நெடுமுடி நிவாரண முகாம்",
    "Champakulam Shelter": "சம்பாக்குளம் தங்குமிடம்",
    "Mala Boat Jetty": "மாலா படகுத்துறை",
    "Chalakudy River Jetty": "சாலக்குடி ஆற்றுத்துறை",
    "Kalpetta Town": "கல்பற்ற நகரம்",
}


def _load():
    return yaml.safe_load(SEEDS.read_text(encoding="utf-8"))


def _mentioned(text: str, landmark: dict, lang: str = "en") -> bool:
    if lang == "ta":
        alias = TA_PLACE.get(landmark["name"])
        if alias:
            return alias in (text or "")
    blob = (text or "").lower()
    terms = [landmark["name"], *landmark.get("aliases_en", []), *landmark.get("aliases_hi", [])]
    return any(term and term.lower() in blob for term in terms)


def _places(text: str, landmarks: list, lang: str = "en") -> set:
    return {lm["name"] for lm in landmarks if _mentioned(text, lm, lang)}


def test_hi_and_ta_use_the_english_place():
    data = _load()
    landmarks = data["landmarks"]
    for inc in data["incidents"]:
        samples = {row["lang"]: row["text"] for row in inc["sample_reports"]}
        assert {"en", "hi", "ta"} <= set(samples), inc["id"]
        english = _places(samples["en"], landmarks)
        for lang in ("hi", "hinglish", "ta"):
            other = _places(samples[lang], landmarks, lang)
            assert not other - english, f"{inc['id']} {lang} names {other - english}"
            assert not english - other, f"{inc['id']} {lang} misses {english - other}"


def test_tamil_seed_lines_are_sentences_not_pasted_english():
    latin = re.compile(r"[A-Za-z]{3,}")
    data = _load()
    for inc in data["incidents"]:
        tamil = next(row["text"] for row in inc["sample_reports"] if row["lang"] == "ta")
        words = latin.findall(tamil)
        assert words == [], f"{inc['id']} still has pasted English {words}"
        assert re.search(r"[\u0B80-\u0BFF]", tamil), inc["id"]


def test_inc005_tamil_names_the_aluva_clock_tower():
    data = _load()
    tamil = next(
        row["text"]
        for row in next(i for i in data["incidents"] if i["id"] == "INC-005")["sample_reports"]
        if row["lang"] == "ta"
    )
    assert "ஆலுவா கடிகாரக் கோபுரம்" in tamil
    assert "சுவர்" in tamil


def test_inc008_hindi_names_st_jude_not_the_school():
    data = _load()
    samples = {row["lang"]: row["text"] for row in next(i for i in data["incidents"] if i["id"] == "INC-008")["sample_reports"]}
    hindi = samples["hi"].lower()
    assert "st. jude" in hindi or "st jude" in hindi
    assert "school" not in hindi
    assert "स्कूल" not in samples["hi"]
    assert "செயின்ட் ஜூட்" in samples["ta"]
    assert "school" not in samples["ta"].lower()
    assert "பள்ளி" not in samples["ta"]
