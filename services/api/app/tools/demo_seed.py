"""Synthetic flood demo pack: 45+ reports, duplicates, one update, one hoax, one silent ward.

Loaded only when DEMO_MODE is on. All names and places are fictional Riverbend.
"""
from __future__ import annotations

from typing import Any, Dict, List

SILENT_WARDS = ["ward_12"]

WARDS = [
    ("ward_1", "Sangam Vihar", 26.845, 80.932),
    ("ward_2", "Gandhi Nagar", 26.852, 80.925),
    ("ward_3", "Riverfront Ghat", 26.839, 80.941),
    ("ward_4", "Old Bazaar", 26.858, 80.948),
    ("ward_5", "Shanti Nagar", 26.861, 80.936),
    ("ward_6", "Civil Lines", 26.849, 80.955),
    ("ward_7", "Industrial Area", 26.834, 80.962),
    ("ward_8", "Green Park Colony", 26.866, 80.951),
    ("ward_9", "Subhash Nagar", 26.842, 80.970),
    ("ward_10", "Model Town", 26.870, 80.928),
    ("ward_11", "Transport Nagar", 26.828, 80.980),
]

TYPES = ["rescue", "food", "medical", "shelter", "info"]
LANGS = ["hi", "hinglish", "en", "ta"]


def _line(index: int, ward_name: str, people: int, kind: str) -> tuple[str, str]:
    lang = LANGS[index % len(LANGS)]
    if lang == "hi":
        text = f"वार्ड संदेश {index}: {ward_name} में {people} लोग पानी में फंसे हैं। नाव चाहिए। यह काल्पनिक रिपोर्ट है।"
    elif lang == "hinglish":
        text = f"Ward message {index}: {ward_name} mein {people} log paani mein fase hain, boat chahiye. Synthetic report."
    elif lang == "ta":
        text = f"செய்தி {index}: {ward_name} இல் {people} பேர் வெள்ளத்தில் சிக்கியுள்ளனர். படகு தேவை. செயற்கை அறிக்கை."
    else:
        text = f"Message {index}: {people} people stranded in {ward_name}. Need a boat. Synthetic Riverbend report."
    return lang, text


def build_demo_reports() -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    # 36 distinct originals across wards 1–11. Ward 12 is the silent zone.
    for i in range(1, 37):
        ward_id, ward_name, lat, lng = WARDS[(i - 1) % len(WARDS)]
        people = 1 + (i % 6)
        lang, text = _line(i, ward_name, people, "original")
        reports.append({
            "id": f"DR-{i:03d}",
            "kind": "original",
            "ward_id": ward_id,
            "lat": round(lat + (i % 5) * 0.0004, 6),
            "lng": round(lng + (i % 3) * 0.0004, 6),
            "lang": lang,
            "people": people,
            "type": TYPES[i % len(TYPES)],
            "text": text,
            "source_id": f"demo_phone_{i:03d}",
            "flags": [],
            "duplicate_of": None,
        })

    # Duplicates of the Ram Ghat / ward 3 house (DR-003 sits in ward_3).
    dup_texts = [
        ("hi", "राम घाट के पास वही घर, छत पर लोग हैं, नाव भेजो। दूसरी रिपोर्ट, काल्पनिक।"),
        ("hinglish", "Ram ghat wala same ghar, log chhat par hain, please boat. Duplicate report, synthetic."),
        ("en", "Same house near Ram Ghat, people on the roof, send a boat. Second reporter, synthetic."),
        ("hi", "रिवरफ्रंट घाट वाली गली में फिर से वही फंसे हुए लोग। नकल रिपोर्ट, काल्पनिक।"),
        ("en", "Another neighbour reporting the Riverfront Ghat lane rescue. Synthetic duplicate."),
        ("hinglish", "Ward 3 Ram ghat lane dobara: same family on roof. Synthetic duplicate."),
        ("en", "Third caller, same Ram Ghat roof, still need a boat. Synthetic duplicate."),
    ]
    for offset, (lang, text) in enumerate(dup_texts, start=1):
        reports.append({
            "id": f"DR-D{offset:02d}",
            "kind": "duplicate",
            "ward_id": "ward_3",
            "lat": 26.8392,
            "lng": 80.9415,
            "lang": lang,
            "people": 8,
            "type": "rescue",
            "text": text,
            "source_id": f"demo_dup_{offset:02d}",
            "flags": [],
            "duplicate_of": "DR-003",
        })

    reports.append({
        "id": "DR-U01",
        "kind": "update",
        "ward_id": "ward_3",
        "lat": 26.8392,
        "lng": 80.9415,
        "lang": "hinglish",
        "people": 5,
        "type": "rescue",
        "text": "Ram ghat par ab 5 log hain, paani badh raha hai. Pehle 3 the. Synthetic update.",
        "source_id": "demo_update_01",
        "flags": ["update"],
        "duplicate_of": "INC-001",
    })

    reports.append({
        "id": "DR-H01",
        "kind": "hoax",
        "ward_id": "ward_4",
        "lat": 26.858,
        "lng": 80.948,
        "lang": "en",
        "people": 0,
        "type": "info",
        "text": "Forward this to 10 groups. Free helicopter rescue call this number. 100% verified news share fast. Synthetic hoax, do not dispatch.",
        "source_id": "demo_hoax_01",
        "flags": ["hoax"],
        "duplicate_of": None,
    })
    return reports


def demo_summary(reports: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    rows = reports if reports is not None else build_demo_reports()
    kinds: Dict[str, int] = {}
    wards = set()
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        wards.add(row["ward_id"])
    return {
        "report_count": len(rows),
        "kinds": kinds,
        "wards_with_reports": sorted(wards),
        "silent_wards": list(SILENT_WARDS),
    }


def load_demo_pack(storage) -> Dict[str, Any]:
    """Insert the synthetic demo reports. Flags hoax; never deletes it."""
    reports = build_demo_reports()
    summary = demo_summary(reports)
    if summary["report_count"] < 45:
        raise RuntimeError("Flood demo pack must contain at least 45 reports")
    if "ward_12" in summary["wards_with_reports"]:
        raise RuntimeError("Ward 12 is the silent zone and must have zero reports")
    for row in reports:
        storage.save_report_raw(
            raw_text=row["text"],
            channel="text",
            lang=row["lang"],
            source_id=row["source_id"],
            trust_level="anonymous",
            pack_id="flood",
            flags=list(row["flags"]),
            report_id=row["id"],
        )
    hoax = storage.get_report("DR-H01")
    if hoax and "hoax" not in hoax.flags:
        hoax.flags.append("hoax")

    hero = storage.get_request("INC-001")
    if hero is not None:
        hero.update_count = max(hero.update_count, 1)
        hero.people_count = 5
        if "update" not in hero.flags:
            hero.flags.append("update")
        storage._requests[hero.id] = hero
    return summary
