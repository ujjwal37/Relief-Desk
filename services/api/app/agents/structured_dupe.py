"""Second duplicate check, on the structured record Gemini (or the rules) produced.

The first check runs at submit time on raw words. Two reports of one house in different
languages share almost no words, so this pass compares the English record instead:
place and landmark, pin distance, the English gist, people, vulnerabilities and depth.
It only FLAGS a possible duplicate. A person decides Merge or Keep separate.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.models.firestore_models import PossibleDuplicate, StoredRequest
from app.tools.place_names import english_place

WINDOW_H = 24.0
GPS_KM = 0.3
LANDMARK_KM = 2.0  # a named landmark only counts when the pins are also in the same neighbourhood
OPEN = ("new", "needs_recheck", "matched")
LANDMARKS = ("jetty", "church", "school", "bridge", "temple", "market", "hospital", "camp", "mosque", "spillway", "junction")
PLACES = ("kainakary", "champakulam", "nedumudi", "pulinkunnu", "kavalam", "ramankary", "thalavady", "moncompu",
          "edathua", "veliyanad", "muttar", "thakazhy", "alappuzha", "kuttanad", "thottappally", "kainakari")
_OTHER_SIDE = re.compile(r"other side|across the (?:canal|river)|opposite bank|different house|next village|മറുകര|അക്കരെ|उस पार|doosri taraf", re.I)
_STOP = set("a an the of to in at on and or is are was were with near our my we us need needs help please house home now".split())


def _status(r) -> str:
    return str(getattr(r.status, "value", r.status) or "")


def _text(r: StoredRequest) -> str:
    return english_place(" ".join(x for x in (r.place_text, r.ai_translation, r.raw_text) if x)).lower()


def _landmarks(r: StoredRequest) -> set:
    t = _text(r)
    places = {p.replace("kainakari", "kainakary") for p in PLACES if p in t}
    marks = {m for m in LANDMARKS if m in t}
    return {(p, m) for p in places for m in marks} or {(p, "") for p in places}


_SPOT = re.compile(r"\b([a-z0-9]*[a-z][a-z0-9]{2,})\s+(?:boat\s+)?(" + "|".join(LANDMARKS) + r")\b")
_GENERIC = {"near", "boat", "rescue", "stranded", "stuck", "people", "send", "the", "this", "that", "from", "nearby"}


def _spots(r: StoredRequest) -> set:
    """Named spots such as 'kainakary jetty'. Two reports naming different spots are different places."""
    return {(a, b) for a, b in _SPOT.findall(_text(r)) if a not in _GENERIC}


def _gist_tokens(r: StoredRequest) -> set:
    t = english_place(r.ai_translation or r.raw_text or "").lower()
    return {w for w in re.findall(r"[a-z]{3,}", t) if w not in _STOP}


def _km(a: StoredRequest, b: StoredRequest) -> Optional[float]:
    if None in (a.lat, a.lng, b.lat, b.lng):
        return None
    from app.tools.geo import haversine_distance
    return float(haversine_distance(a.lat, a.lng, b.lat, b.lng))


def _minutes(a: StoredRequest, b: StoredRequest) -> Optional[float]:
    try:
        ta = datetime.fromisoformat(str(a.created_at).replace("Z", "+00:00"))
        tb = datetime.fromisoformat(str(b.created_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    ta = ta if ta.tzinfo else ta.replace(tzinfo=timezone.utc)
    tb = tb if tb.tzinfo else tb.replace(tzinfo=timezone.utc)
    return abs((ta - tb).total_seconds()) / 60.0


def _vuln(r: StoredRequest) -> set:
    v = r.vulnerable
    return {n for n in ("child", "elderly", "disabled", "pregnant", "medical_need") if getattr(v, n, False)}


def _band(r: StoredRequest) -> str:
    from app.agents.depth import band_of
    return band_of(r)


def compare(new: StoredRequest, old: StoredRequest) -> Optional[Tuple[float, PossibleDuplicate]]:
    """Signals and differences for one pair, or None when nothing places them together."""
    mins = _minutes(new, old)
    if mins is not None and mins > WINDOW_H * 60:
        return None
    km = _km(new, old)
    sa, sb = _spots(new), _spots(old)
    if (sa or sb) and not (sa & sb):
        return None  # different named spots, or only one report names a spot
    signals: List[str] = []
    reasons: List[str] = []
    if km is not None and km <= GPS_KM:
        signals.append("gps")
        reasons.append(f"~{int(round(km * 1000 / 10.0) * 10)} m apart")
    shared = _landmarks(new) & _landmarks(old)
    named = sorted((p, m) for p, m in shared if m)
    same_ward = bool(new.ward_id and new.ward_id == old.ward_id)
    if named and same_ward and (km is None or km <= LANDMARK_KM):
        p, m = named[0]
        signals.append("landmark")
        reasons.insert(0, f"same landmark: {p.title()} {m}")
        if "gps" not in signals and km is not None:
            reasons.append(f"~{int(round(km * 1000 / 10.0) * 10)} m apart")
    if not signals:
        return None
    a, b = _gist_tokens(new), _gist_tokens(old)
    gist = len(a & b) / len(a | b) if a and b else 0.0
    if gist >= 0.25:
        signals.append("gist")
    if mins is not None:
        reasons.append(f"{int(round(mins))} min apart")
    both_v = sorted(_vuln(new) & _vuln(old))
    if both_v:
        reasons.append("both mention " + ", ".join(x.replace("_", " ") for x in both_v))

    differences: List[str] = []
    plan = None
    pa, pb = old.people_count, new.people_count
    if pa and pb and pa != pb:
        plan = max(pa, pb)
        differences.append(f"{pa} vs {pb} people → plan for {plan}")
    elif bool(pa) != bool(pb):
        plan = pa or pb
        differences.append(f"people not stated in one report → plan for {plan}")
    elif pa and pa == pb:
        plan = pa
    only_new = sorted(_vuln(new) - _vuln(old))
    only_old = sorted(_vuln(old) - _vuln(new))
    if only_new:
        differences.append("only this report: " + ", ".join(x.replace("_", " ") for x in only_new))
    if only_old:
        differences.append("only the other: " + ", ".join(x.replace("_", " ") for x in only_old))
    da, db = _band(old), _band(new)
    if "unknown" not in (da, db) and da != db:
        differences.append(f"depth {da} vs {db}")
    other_side = bool(_OTHER_SIDE.search(" ".join(x for x in (new.raw_text, new.ai_translation) if x)))
    if other_side:
        differences.append("this report says it is on the other side")

    high = (("gps" in signals or "landmark" in signals) and "gist" in signals and not other_side
            and not only_new and not only_old)
    level = "High" if high else "Medium"
    confidence = 0.78 if high else 0.6  # a flag only; a person decides
    code = old.public_code
    if not code:
        from app.api.public import case_code
        code = case_code(old)
    note = f"Possible duplicate, review ({code}). Match evidence: " + " · ".join(reasons)
    if differences:
        note += ". Differences: " + "; ".join(differences)
    hint = PossibleDuplicate(target_id=old.id, target_code=code, confidence=confidence, similarity=round(gist, 2),
                             distance_km=round(km, 2) if km is not None else None,
                             minutes=round(mins, 1) if mins is not None else None, note=note,
                             signals=signals, level=level, differences=differences, plan_people=plan)
    score = confidence + 0.05 * len(signals) - (km or 0) * 0.01
    return score, hint


def find_structured_twin(req: StoredRequest, others) -> Optional[PossibleDuplicate]:
    best = None
    for o in others:
        if o.id == req.id or o.merged_into or _status(o) not in OPEN or "hoax" in (o.flags or []):
            continue
        if (o.created_at or "") > (req.created_at or "~"):
            continue
        got = compare(req, o)
        if got and (best is None or got[0] > best[0]):
            best = got
    return best[1] if best else None


def merged_facts(req: StoredRequest, twin: StoredRequest) -> StoredRequest:
    """Most people, every vulnerability, the worst quoted depth: the facts both reports are planned on."""
    from app.agents.depth import BANDS
    m = req.model_copy(deep=True)
    counts = [c for c in (req.people_count, twin.people_count) if c]
    m.people_count = max(counts) if counts else None
    for n in ("child", "elderly", "disabled", "pregnant", "medical_need"):
        if getattr(twin.vulnerable, n, False):
            setattr(m.vulnerable, n, True)
    order = {b: i for i, b in enumerate(BANDS)}
    if twin.water_depth and order.get(_band(twin), 0) > order.get(_band(req), 0) and _band(twin) != "unknown":
        m.water_depth = dict(twin.water_depth)
    m.raw_text = " ".join(x for x in (req.raw_text, twin.raw_text) if x)
    return m
