"""Hindi and Tamil seed lines must name the same place as the English line."""
from pathlib import Path

import yaml

SEEDS = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"


def _load():
    return yaml.safe_load(SEEDS.read_text(encoding="utf-8"))


def _mentioned(text: str, landmark: dict) -> bool:
    blob = (text or "").lower()
    terms = [landmark["name"], *landmark.get("aliases_en", []), *landmark.get("aliases_hi", [])]
    return any(term and term.lower() in blob for term in terms)


def _places(text: str, landmarks: list) -> set:
    return {lm["name"] for lm in landmarks if _mentioned(text, lm)}


def test_hi_and_ta_use_the_english_place():
    data = _load()
    landmarks = data["landmarks"]
    for inc in data["incidents"]:
        samples = {row["lang"]: row["text"] for row in inc["sample_reports"]}
        assert {"en", "hi", "ta"} <= set(samples), inc["id"]
        english = _places(samples["en"], landmarks)
        for lang in ("hi", "hinglish", "ta"):
            other = _places(samples[lang], landmarks)
            assert not other - english, f"{inc['id']} {lang} names {other - english}"
            assert not english - other, f"{inc['id']} {lang} misses {english - other}"


def test_inc008_hindi_names_st_jude_not_the_school():
    data = _load()
    samples = {row["lang"]: row["text"] for row in next(i for i in data["incidents"] if i["id"] == "INC-008")["sample_reports"]}
    for lang in ("hi", "ta"):
        text = samples[lang].lower()
        assert "st. jude" in text or "st jude" in text
        assert "school" not in text
        assert "स्कूल" not in samples[lang]
