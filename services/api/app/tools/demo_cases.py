"""Believable synthetic Kerala flood cases for a cold start in DEMO_MODE.

Cloud Run keeps cases in memory, so every new instance starts here. Places are real Kerala
panchayats; people, phone sources and messages are fictional. Every row is synthetic=True and
carries the "synthetic" flag. Timestamps are relative to the moment the instance starts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

DEMO_TEAM_IDS = (
    "RES-BOAT-02",
    "RES-BOAT-03",
    "RES-MED-01",
    "RES-BOAT-05",
    "RES-BOAT-06",
    "RES-MED-06",
)

# (id, minutes ago, type, ward, lat, lng, people, hazard, vulnerable, status, en, hi, raw language)
DEMO_CASES: List[Dict[str, Any]] = [
    {
        "id": "DEMO-101", "minutes": 7, "type": "rescue", "ward_id": "ward_2", "lat": 9.418, "lng": 76.409,
        "people": 5, "hazard": "water_rising", "vulnerable": {"elderly": True},
        "place": "Champakulam church road",
        "en": "5 people on the first floor near Champakulam church road, water rising fast, grandmother cannot walk.",
        "hi": "चंपक्कुलम चर्च रोड के पास 5 लोग पहली मंज़िल पर हैं, पानी तेज़ी से बढ़ रहा है, दादी चल नहीं सकतीं।",
        "raw": "ml",
        "ml": "ചമ്പക്കുളം പള്ളി റോഡിന് സമീപം ഒന്നാം നിലയിൽ 5 പേർ കുടുങ്ങി, വെള്ളം വേഗത്തിൽ ഉയരുന്നു, അമ്മൂമ്മയ്ക്ക് നടക്കാൻ കഴിയില്ല. ദയവായി ബോട്ട് അയയ്ക്കൂ.",
        # The hero case: one Malayalam SOS and two reworded reports of the same house, merged by the desk.
        "merged": [
            {"minutes": 5, "lang": "ml", "channel": "voice",
             "text": "Champakulam church road il 5 per first floor il und, vellam koodunnu, ammachi nadakkan pattilla"},
            {"minutes": 3, "lang": "en", "channel": "text",
             "text": "Family of five stuck upstairs by Champakulam church, grandmother can't walk, water coming up fast."},
        ],
    },
    {
        "id": "DEMO-102", "minutes": 15, "type": "medical", "ward_id": "ward_1", "lat": 9.472, "lng": 76.392,
        "people": 1, "hazard": "stranded", "vulnerable": {"medical_need": True},
        "place": "Kainakary north, near the boat jetty",
        "en": "My father is on oxygen and the cylinder has about 3 hours left. House near Kainakary jetty is surrounded by water.",
        "hi": "मेरे पिता ऑक्सीजन पर हैं और सिलेंडर में लगभग 3 घंटे बचे हैं। कैनकरी जेट्टी के पास घर पानी से घिरा है।",
        "raw": "en",
    },
    {
        "id": "DEMO-103", "minutes": 24, "type": "food", "ward_id": "ward_3", "lat": 9.433, "lng": 76.402,
        "people": 40, "hazard": "none", "vulnerable": {"child": True},
        "place": "Nedumudi Government LP School camp",
        "en": "Relief camp at Nedumudi Government LP School: about 40 people, food packets finished since last night, 6 small children.",
        "hi": "नेदुमुडी सरकारी एलपी स्कूल राहत शिविर में लगभग 40 लोग हैं, कल रात से खाने के पैकेट खत्म हैं, 6 छोटे बच्चे हैं।",
        "raw": "en",
    },
    {
        "id": "DEMO-104", "minutes": 38, "type": "shelter", "ward_id": "ward_1", "lat": 9.469, "lng": 76.387,
        "people": 12, "hazard": "water_rising", "vulnerable": {"pregnant": True},
        "place": "Kainakary south, ward 1",
        "en": "Ground floor of our house is submerged. 12 of us including a pregnant woman need a place to stay tonight.",
        "hi": "हमारे घर का भूतल डूब गया है। एक गर्भवती महिला सहित हम 12 लोगों को आज रात रहने की जगह चाहिए।",
        "raw": "hi",
    },
    {
        "id": "DEMO-105", "minutes": 52, "type": "rescue", "ward_id": "ward_3", "lat": 9.428, "lng": 76.394,
        "people": 3, "hazard": "stranded", "vulnerable": {"child": True},
        "place": "Nedumudi, behind the temple",
        "en": "3 people including a 4-year-old child stranded on the terrace behind Nedumudi temple. Water steady, no boat seen yet.",
        "hi": "नेदुमुडी मंदिर के पीछे छत पर एक 4 साल के बच्चे सहित 3 लोग फंसे हैं। पानी स्थिर है, अभी तक कोई नाव नहीं दिखी।",
        "raw": "en",
    },
    {
        # No-team demo: a life threat in deep water where no boat is within reach. The desk must not
        # invent a team; the coordinator gets the no-team options (Call 112, road team, wider search).
        "id": "DEMO-108", "minutes": 3, "type": "medical", "ward_id": None, "lat": 9.318, "lng": 76.383,
        "people": 1, "hazard": "water_rising", "vulnerable": {"child": True, "medical_need": True},
        "place": "Thottappally spillway, south of Kuttanad",
        "en": "My son is not breathing properly, water is chest deep around our house near Thottappally spillway. Please help.",
        "hi": "मेरा बेटा ठीक से सांस नहीं ले रहा, थोट्टपल्ली स्पिलवे के पास हमारे घर के चारों ओर छाती तक पानी है। कृपया मदद करें।",
        "raw": "en",
    },
    {
        # Malayalam life threat: the lane must fire on the original script, not only on a translation.
        "id": "DEMO-109", "minutes": 2, "type": "medical", "ward_id": "ward_1", "lat": 9.474, "lng": 76.385,
        "people": 1, "hazard": "water_rising", "vulnerable": {"medical_need": True},
        "place": "Kainakary panchayat office",
        "en": "My father is not breathing, water all around the house near Kainakary panchayat office. Come fast.",
        "hi": "मेरे पिता सांस नहीं ले रहे, कैनकरी पंचायत ऑफिस के पास घर के चारों ओर पानी है। जल्दी आइए।",
        "raw": "ml",
        "ml": "അച്ഛൻ ശ്വസിക്കുന്നില്ല, കൈനകരി പഞ്ചായത്ത് ഓഫീസിന് അടുത്ത് വീടിന് ചുറ്റും വെള്ളം. വേഗം വരൂ.",
    },
    {
        "id": "DEMO-106", "minutes": 110, "type": "info", "ward_id": "ward_2", "lat": 9.414, "lng": 76.415,
        "people": None, "hazard": "none", "vulnerable": {},
        "place": "Champakulam - Alappuzha road",
        "en": "Champakulam to Alappuzha road is blocked by 3 feet of water near the bridge, vehicles turning back.",
        "hi": "चंपक्कुलम से अलप्पुझा सड़क पुल के पास 3 फीट पानी से बंद है, गाड़ियां वापस लौट रही हैं।",
        "raw": "en",
        "status": "completed",
    },
    {
        # A forwarded spam message, so the hoax flag is visible in every demo.
        "id": "DEMO-107", "minutes": 6, "type": "info", "ward_id": None, "lat": None, "lng": None,
        "people": None, "hazard": "none", "vulnerable": {},
        "place": None,
        "en": "NASA announced a free helicopter rescue. Call this number and forward this to 10 groups. 100% verified news share fast.",
        "hi": "NASA announced a free helicopter rescue. Call this number and forward this to 10 groups. 100% verified news share fast.",
        "raw": "en",
        "hoax_reason": "Known spam phrase: forward this to 10 groups",
    },
]


def load_demo_cases(storage) -> int:
    """Insert the demo teams and cases. Skips any id already present, so a reload never duplicates."""
    from app.models.firestore_models import RequestStatus, StoredRequest
    from app.models.schemas import FieldConfidences, HazardType, IncidentType, VulnerableFlags
    from app.tools.scoring import scoring_engine

    from app.agents.pipeline import ensure_trace

    try:
        storage.load_seed_resources(only_ids=[tid for tid in DEMO_TEAM_IDS if storage.get_resource(tid) is None])
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    added = 0

    from app.tools.storage import in_desk_area

    for row in DEMO_CASES:
        if storage.get_request(row["id"]) is not None:
            continue
        if not in_desk_area(row.get("lat"), row.get("lng")):
            continue
        stamp = (now - timedelta(minutes=row["minutes"])).isoformat()
        raw = row.get(row["raw"]) or row["en"]
        req = StoredRequest(
            id=row["id"],
            type=IncidentType(row["type"]),
            place_text=row["place"],
            ward_id=row["ward_id"],
            lat=row["lat"],
            lng=row["lng"],
            people_count=row["people"],
            vulnerable=VulnerableFlags(**row["vulnerable"]),
            hazard=HazardType(row["hazard"]),
            status=RequestStatus(row.get("status", "new")),
            flags=["synthetic"] + (["hoax", "likely_hoax"] if row.get("hoax_reason") else []),
            hoax_reason=row.get("hoax_reason"),
            raw_text=raw,
            ai_translation=row["en"],
            summary=row["en"],
            translations={k: row[k] for k in ("en", "hi", "ml") if row.get(k)},
            translation_confidence=0.9,
            confidence=FieldConfidences(type=0.9, place=0.85, people=0.85, vulnerable=0.85, urgency=0.85),
            report_ids=[f"{row['id']}-R1"],
            synthetic=True,
            created_at=stamp,
            updated_at=stamp,
            ai_source="offline_fallback",
        )
        if row.get("merged"):
            _attach_merged(storage, req, row, now)
        scored = scoring_engine.compute_urgency(req)
        req.urgency_score = scored.score
        req.urgency_reason = scored.reason
        storage._requests[req.id] = req
        added += 1
    from app.llm.replay_seed import attach_recorded_ai
    attach_recorded_ai(storage)
    for row in DEMO_CASES:
        req = storage.get_request(row["id"])
        if req is not None and not req.trace:
            ensure_trace(req)
    from app.tools.case_queue import mark_seed_life_threats
    mark_seed_life_threats(storage._requests.values())
    return added


def _attach_merged(storage, req, row, now) -> None:
    """Store the first report and its reworded duplicates as real reports, merged into one case."""
    from app.models.firestore_models import ReportQuote, StoredReport

    rows = [{"minutes": row["minutes"], "lang": row["raw"], "channel": "text", "text": req.raw_text}] + list(row["merged"])
    ids, quotes = [], []
    for i, item in enumerate(rows, start=1):
        rid = f"{row['id']}-R{i}"
        at = (now - timedelta(minutes=item["minutes"])).isoformat()
        storage._reports[rid] = StoredReport(
            id=rid, raw_text=item["text"], channel=item["channel"], lang=item["lang"], request_id=req.id,
            case_id=req.id, joined_existing=i > 1, incident_type=req.type.value, place_text=req.place_text,
            ward_id=req.ward_id, synthetic=True, flags=["synthetic"], created_at=at,
        )
        ids.append(rid)
        quotes.append(ReportQuote(report_id=rid, text=item["text"], people_span="5" if i < 3 else "five"))
    req.report_ids = ids
    req.report_quotes = quotes
    req.merged_count = len(ids)
    req.dedupe_trace = ("Same house: all three name Champakulam church road, 5 people (five), "
                        "an elderly woman who cannot walk and rising water, within 4 minutes. Counts agree.")
