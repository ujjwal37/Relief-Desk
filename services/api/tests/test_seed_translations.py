"""Hindi seed lines name the same place as the English line. Tamil is not a seed language."""
import re
from pathlib import Path

import yaml

SEEDS = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"
TAMIL = re.compile(r"[\u0B80-\u0BFF]")


def _load():
    return yaml.safe_load(SEEDS.read_text(encoding="utf-8"))


def _mentioned(text: str, landmark: dict) -> bool:
    blob = (text or "").lower()
    terms = [landmark["name"], *landmark.get("aliases_en", []), *landmark.get("aliases_hi", [])]
    return any(term and term.lower() in blob for term in terms)


def _places(text: str, landmarks: list) -> set:
    return {lm["name"] for lm in landmarks if _mentioned(text, lm)}


def test_hi_uses_the_english_place_and_tamil_is_gone():
    data = _load()
    landmarks = data["landmarks"]
    assert TAMIL.search(SEEDS.read_text(encoding="utf-8")) is None
    for inc in data["incidents"]:
        samples = {row["lang"]: row["text"] for row in inc["sample_reports"]}
        assert "ta" not in samples, inc["id"]
        assert {"en", "hi"} <= set(samples), inc["id"]
        english = _places(samples["en"], landmarks)
        for lang in ("hi", "hinglish"):
            other = _places(samples[lang], landmarks)
            assert not other - english, f"{inc['id']} {lang} names {other - english}"
            assert not english - other, f"{inc['id']} {lang} misses {english - other}"


def test_inc008_hindi_names_st_jude_not_the_school():
    data = _load()
    samples = {row["lang"]: row["text"] for row in next(i for i in data["incidents"] if i["id"] == "INC-008")["sample_reports"]}
    hindi = samples["hi"].lower()
    assert "st. jude" in hindi or "st jude" in hindi
    assert "school" not in hindi
    assert "स्कूल" not in samples["hi"]


def test_desk_shows_english_plus_one_hindi_report():
    from app.tools.storage import StorageService

    storage = StorageService()
    storage.load_seed_incidents()
    hindi = []
    for req in storage._requests.values():
        blob = f"{req.raw_text or ''}\n{req.ai_translation or ''}"
        assert TAMIL.search(blob) is None, req.id
        assert "ta" not in (req.translations or {})
        if req.raw_text and re.search(r"[\u0900-\u097F]", req.raw_text):
            hindi.append(req.id)
    assert hindi == ["INC-001"]
