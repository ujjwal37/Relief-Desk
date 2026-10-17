"""Ask the desk: a coordinator question becomes read-only filters over the case store.

Gemini picks the filters with one function call (search_cases). Without Gemini, or when the
call fails, keyword rules pick them. Either way the store is only read, never changed.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config import settings
from app.models.firestore_models import IncidentType, RequestStatus

TYPES = [t.value for t in IncidentType]
VULNERABLE = ["child", "elderly", "disabled", "pregnant", "medical_need"]
OPEN = {RequestStatus.NEW.value, RequestStatus.NEEDS_RECHECK.value, RequestStatus.MATCHED.value}
STATUSES = [s.value for s in RequestStatus]
# Plain words a coordinator uses for a case's stage, mapped to the stored statuses.
STATUS_GROUPS = {
    "completed": [RequestStatus.COMPLETED.value, RequestStatus.RESOLVED.value, RequestStatus.CLOSED.value],
    "dispatched": [RequestStatus.APPROVED.value, RequestStatus.DISPATCHED.value, RequestStatus.IN_PROGRESS.value],
}
STATUS_WORDS = {
    "completed": ["completed", "complete", "done", "finished", "resolved", "closed", "rescued", "helped already",
                  "पूरा", "पूरे", "हो गया", "ho gaya", "ho gaye", "khatam"],
    "dispatched": ["dispatched", "assigned", "en route", "on the way", "in progress", "underway", "team sent",
                   "भेजा", "भेजी", "भेजे", "bheja", "bheje", "raste mein"],
}

TYPE_WORDS = {
    "rescue": ["rescue", "trapped", "stranded", "boat", "roof", "बचाव", "फंसे", "bachao", "phanse", "രക്ഷ"],
    "food": ["food", "drinking water", "hungry", "ration", "खाना", "पीने का पानी", "khana", "ഭക്ഷണം"],
    "medical": ["medical", "medicine", "insulin", "doctor", "injured", "दवा", "dawai", "dawa", "मेडिकल", "മരുന്ന്"],
    "shelter": ["shelter", "camp", "आश्रय", "आसरा", "ക്യാമ്പ്"],
}
VULN_WORDS = {
    "elderly": ["elderly", "old", "senior", "aged", "बुजुर्ग", "बूढ़े", "buzurg", "bujurg", "budhe", "പ്രായമായ"],
    "child": ["child", "children", "kid", "baby", "infant", "बच्चे", "बच्चा", "bacche", "bachche", "കുട്ടി"],
    "pregnant": ["pregnant", "गर्भवती", "garbhvati", "ഗർഭിണി"],
    "disabled": ["disabled", "wheelchair", "विकलांग", "divyang"],
    "medical_need": ["dialysis", "oxygen", "bedridden"],
}
# "not done yet", "abhi tak nahi", "पूरे नहीं": a negated stage means the opposite group (still waiting).
NEGATION = re.compile(
    r"\b(?:not|never|yet to|still not|haven'?t|hasn'?t|isn'?t|aren'?t|wasn'?t|nahi|nahin|nhi)\b|नहीं|नही|अभी तक",
    re.I,
)
BAND_WORDS = {
    "critical": ["critical", "most urgent", "immediate", "life-threatening", "गंभीर", "क्रिटिकल", "gambhir", "critical cases", "ഗുരുതര"],
    "urgent": ["urgent", "अर्जेंट", "जरूरी", "zaroori", "jaruri", "അടിയന്തര"],
}
# Same thresholds as the web band util (libs/shared band.util.ts): Critical >= 80, Urgent >= 60.
BAND_MIN = {"critical": 80.0, "urgent": 60.0}


def band_of_score(score: float) -> str:
    s = float(score or 0)
    if s >= BAND_MIN["critical"]:
        return "critical"
    if s >= BAND_MIN["urgent"]:
        return "urgent"
    return "other"


WAITING_WORDS = ["waiting", "still", "open", "pending", "unassigned", "not yet", "इंतज़ार", "इंतजार", "intezaar",
                 "intezar", "baaki", "बाकी", "കാത്തിരി"]

FUNCTION = {
    "name": "search_cases",
    "description": "Read-only search over the relief desk's cases.",
    "parameters": {
        "type": "object",
        "properties": {
            "types": {"type": "array", "items": {"type": "string", "enum": TYPES}, "description": "Need types to include. Empty means any."},
            "ward_ids": {"type": "array", "items": {"type": "string"}, "description": "Ward ids such as ward_4. Empty means any ward."},
            "vulnerable": {"type": "array", "items": {"type": "string", "enum": VULNERABLE}, "description": "Only cases that include all of these groups."},
            "waiting_only": {"type": "boolean", "description": "True when the question asks for cases not yet dispatched or resolved (pending, open, waiting)."},
            "statuses": {"type": "array", "items": {"type": "string", "enum": STATUSES},
                         "description": "Case stages to include. completed/done/resolved/closed means [completed, resolved, closed]; dispatched/assigned/on the way means [approved, dispatched, in_progress]; pending/open/waiting means [new, needs_recheck, matched]. Empty means any stage."},
            "min_people": {"type": "integer", "description": "Only cases with at least this many people."},
            "bands": {"type": "array", "items": {"type": "string", "enum": ["critical", "urgent"]}, "description": "Urgency bands asked for: critical (score 80+), urgent (60-79). Empty means any."},
            "reason": {"type": "string", "description": "One short English sentence saying what was searched for."},
        },
        "required": ["reason"],
    },
}


def _wards() -> Dict[str, Dict[str, Any]]:
    from app.tools.gazetteer import gazetteer

    return gazetteer.wards


def ward_catalogue() -> str:
    return "; ".join(f"{wid}={w['name_en']} ({w.get('district')})" for wid, w in _wards().items())


def system_prompt() -> str:
    return (
        "You turn a flood-relief coordinator's question into one call to search_cases. "
        "The question may be in English, Hindi, Hinglish or Malayalam. "
        "Map place names to ward ids, and a district name to all of its wards. Wards: "
        + ward_catalogue()
        + ". 'Waiting', 'still', 'pending' or 'not yet helped' means waiting_only=true. "
        "'Completed', 'done', 'resolved' or 'closed' means statuses=[completed, resolved, closed]. "
        "'Dispatched', 'assigned' or 'on the way' means statuses=[approved, dispatched, in_progress]. "
        "A negated stage means the opposite: 'not done yet', 'not completed', 'abhi tak nahi hua' means waiting_only=true and no statuses. "
        "A 'how many' question uses the same filters; the count is the number of matches. "
        "Only use filters the question asks for. Always call the function."
    )


def _has(text: str, words: Iterable[str]) -> bool:
    for w in words:
        if not w:
            continue
        if re.search(r"[a-z]", w):
            if re.search(rf"\b{re.escape(w)}", text):
                return True
        elif re.search(rf"(?<![\u0900-\u097F\u0D00-\u0D7F]){re.escape(w)}", text):
            # Devanagari or Malayalam: the word must start at a word boundary (not inside another word).
            return True
    return False


def rule_filters(question: str) -> Dict[str, Any]:
    q = (question or "").lower()
    types = [t for t, words in TYPE_WORDS.items() if _has(q, words)]
    vulnerable = [v for v, words in VULN_WORDS.items() if _has(q, words)]
    ward_ids: List[str] = []
    for wid, w in _wards().items():
        names = [
            w["name_en"].lower(),
            (w.get("name_hi") or "").lower(),
            (w.get("name_ml") or "").lower(),
            (w.get("district") or "").lower(),
        ]
        if _has(q, names):
            ward_ids.append(wid)
    statuses: List[str] = []
    for group, words in STATUS_WORDS.items():
        if _has(q, words):
            statuses.extend(STATUS_GROUPS[group])
    negated = bool(statuses) and bool(NEGATION.search(q))
    if negated:
        # "Which cases are not done yet?" asks for open cases, not completed ones.
        statuses = []
    waiting = (_has(q, WAITING_WORDS) or negated) and not statuses
    m = re.search(r"(?:at least|atleast|more than|over|minimum|kam se kam|से ज़्यादा|से ज्यादा)\s*(\d+)|(\d+)\s*(?:\+|or more|ya zyada|से अधिक)", q)
    bands = [b for b, words in BAND_WORDS.items() if _has(q, words)]
    out: Dict[str, Any] = {
        "bands": bands,
        "types": types,
        "ward_ids": ward_ids,
        "vulnerable": vulnerable,
        "waiting_only": waiting,
        "statuses": statuses,
        "min_people": int(m.group(1) or m.group(2)) if m else None,
    }
    out["reason"] = describe(out)
    return out


def describe(f: Dict[str, Any]) -> str:
    parts = []
    if f.get("waiting_only"):
        parts.append("waiting")
    st = set(f.get("statuses") or [])
    if st and st <= set(STATUS_GROUPS["completed"]):
        parts.append("completed")
    elif st and st <= set(STATUS_GROUPS["dispatched"]):
        parts.append("dispatched")
    elif st:
        parts.append("/".join(sorted(st)))
    if f.get("bands"):
        parts.append(" or ".join(f["bands"]))
    parts.append((" or ".join(f["types"]) + " cases") if f.get("types") else "cases")
    if f.get("vulnerable"):
        parts.append("with " + " and ".join(v.replace("_", " ") for v in f["vulnerable"]))
    if f.get("ward_ids"):
        parts.append("in " + ", ".join(_wards().get(w, {}).get("name_en", w) for w in f["ward_ids"]))
    if f.get("min_people"):
        parts.append(f"with {f['min_people']}+ people")
    return "Searched " + " ".join(parts) + "."


def clean_filters(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known values so a model reply cannot widen or change the query."""
    wards = _wards()
    out: Dict[str, Any] = {
        "bands": [b for b in (raw.get("bands") or []) if b in BAND_MIN],
        "types": [t for t in (raw.get("types") or []) if t in TYPES],
        "ward_ids": [w for w in (raw.get("ward_ids") or []) if w in wards],
        "vulnerable": [v for v in (raw.get("vulnerable") or []) if v in VULNERABLE],
        "waiting_only": bool(raw.get("waiting_only")),
        "statuses": sorted({s for s in (raw.get("statuses") or []) if s in STATUSES}),
        "min_people": None,
    }
    try:
        mp = int(raw["min_people"]) if raw.get("min_people") not in (None, "") else None
        out["min_people"] = mp if mp and mp > 0 else None
    except (TypeError, ValueError, KeyError):
        pass
    reason = str(raw.get("reason") or "").strip()
    # A stage list and "waiting" together would always be empty. The stage list wins.
    if out["statuses"] and out["waiting_only"]:
        out["waiting_only"] = False
    out["reason"] = reason[:200] if reason else describe(out)
    return out


def _call_function(question: str, timeout_s: float):
    from google.genai import types as gt  # type: ignore
    from app.llm import client as llm

    client = llm.llm_client._make_genai_client(timeout_s)
    resp = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=question,
        config=gt.GenerateContentConfig(
            system_instruction=system_prompt(),
            temperature=0.0,
            tools=[gt.Tool(function_declarations=[gt.FunctionDeclaration(**FUNCTION)])],
            tool_config=gt.ToolConfig(function_calling_config=gt.FunctionCallingConfig(mode="ANY")),
        ),
    )
    calls = getattr(resp, "function_calls", None) or []
    usage = getattr(resp, "usage_metadata", None)
    tokens = getattr(usage, "total_token_count", None) if usage is not None else None
    if not calls:
        raise RuntimeError("no function call")
    return dict(calls[0].args or {}), tokens


def _test_model_filters(question: str, key: str, post=None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """openai_compat: one forced search_cases tool call, or the same schema as JSON when the
    server has no tool support. Cached in memory by question hash. `post` is for tests."""
    from app.llm import client as llm
    from app.llm import openai_compat as oc
    from app.llm.ai_queue import DESK

    c = llm.llm_client
    cache_key = f"{oc.PROVIDER}:{oc.model()}:{key}"
    meta: Dict[str, Any] = {"provider": oc.PROVIDER, "model": oc.model(), "vendor": oc.vendor(),
                            "latency_ms": 0, "tokens": None, "fallback_reason": None}
    started = time.monotonic()
    remembered = c._local_cache.get(cache_key)
    if remembered is not None:
        meta.update(latency_ms=int((time.monotonic() - started) * 1000), mode="cache")
        return clean_filters(json.loads(remembered)), meta
    try:
        with c.guard.slots.slot(DESK):
            started = time.monotonic()
            args, tokens, mode = oc.call_function(system_prompt(), question, FUNCTION, post=post)
        filters = clean_filters(args)
    except Exception as exc:
        meta.update(provider="fallback", model=None, vendor=None, fallback_reason=oc.failure_reason(exc),
                    latency_ms=int((time.monotonic() - started) * 1000))
        return None, meta
    c._local_cache[cache_key] = json.dumps(filters)
    meta.update(tokens=tokens, mode=mode, latency_ms=int((time.monotonic() - started) * 1000))
    return filters, meta


def gemini_filters(question: str, call=None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """One function call. Returns (filters or None, ai metadata). `call` is for tests."""
    from app.llm import client as llm

    from app.llm.ai_queue import DESK

    c = llm.llm_client
    meta: Dict[str, Any] = {"provider": "fallback", "model": None, "latency_ms": 0, "tokens": None, "fallback_reason": None}
    from app.llm import antigravity as ag
    from app.llm import openai_compat as oc

    key = c.cache_key("desk_query:" + system_prompt(), question.strip())
    if call is None and oc.enabled():
        return _test_model_filters(question, key)
    if call is None and ag.antigravity_enabled():
        started = time.monotonic()
        remembered = c._local_cache.get(key)
        if remembered is not None:
            meta.update(provider=ag.PROVIDER, model=ag.MODEL, latency_ms=int((time.monotonic() - started) * 1000))
            return clean_filters(json.loads(remembered)), meta
        schema = json.dumps(FUNCTION["parameters"])
        try:
            # The coordinator is waiting on this answer, so it goes ahead of queued reports.
            with c.guard.slots.slot(DESK):
                raw, tokens = ag.call_antigravity(
                    system_prompt(), f"Question: {question}\n\nReturn the search_cases arguments as one JSON object matching: {schema}")
            filters = clean_filters(json.loads(ag.extract_json(raw)))
        except Exception:
            meta["fallback_reason"] = "error"
            meta["latency_ms"] = int((time.monotonic() - started) * 1000)
            return None, meta
        c._local_cache[key] = json.dumps(filters)
        meta.update(provider=ag.PROVIDER, model=ag.MODEL, tokens=tokens,
                    latency_ms=int((time.monotonic() - started) * 1000))
        return filters, meta
    if call is None and not c.gemini_live():
        meta["fallback_reason"] = "no_api_key"
        return None, meta
    if c.guard.circuit_open():
        meta["fallback_reason"] = "circuit_open"
        return None, meta
    cached = c.get_cached(key) if call is None else None
    if cached:
        try:
            filters = clean_filters(json.loads(cached))
            meta.update(provider="cache", model=settings.GEMINI_MODEL)
            return filters, meta
        except ValueError:
            pass
    started = time.monotonic()
    timeout_s = float(settings.GEMINI_TIMEOUT_S or 12.0)
    call = call or _call_function
    try:
        with c.guard.slots.slot(DESK):
            started = time.monotonic()
            fut = llm._GEMINI_POOL.submit(call, question, timeout_s)
            args, tokens = fut.result(timeout=timeout_s)
        c.guard.record_success()
    except Exception as exc:  # quota, timeout, SDK error: the rules answer instead
        meta["fallback_reason"] = c.note_failure(exc)
        meta["latency_ms"] = int((time.monotonic() - started) * 1000)
        return None, meta
    filters = clean_filters(args)
    try:
        c.set_cached(key, json.dumps(filters))
    except Exception:
        pass
    meta.update(provider="gemini", model=settings.GEMINI_MODEL, tokens=tokens,
                latency_ms=int((time.monotonic() - started) * 1000))
    return filters, meta


def run_filters(requests: Iterable[Any], f: Dict[str, Any], limit: int = 12) -> Tuple[List[Any], int]:
    hits = []
    for r in requests:
        if r.merged_into:
            continue
        if f["types"] and r.type.value not in f["types"]:
            continue
        if f["ward_ids"] and r.ward_id not in f["ward_ids"]:
            continue
        if any(not getattr(r.vulnerable, v, False) for v in f["vulnerable"]):
            continue
        if f["waiting_only"] and r.status.value not in OPEN:
            continue
        if f.get("statuses") and r.status.value not in f["statuses"]:
            continue
        if f["min_people"] and (r.people_count or 0) < f["min_people"]:
            continue
        if f.get("bands") and band_of_score(r.urgency_score) not in f["bands"]:
            continue
        if f.get("bands") and (getattr(r, "hoax_reason", None) or "likely_hoax" in (r.flags or []) or "hoax" in (r.flags or [])):
            continue  # a held hoax is never counted as Critical
        hits.append(r)
    hits.sort(key=lambda r: (-(r.urgency_score or 0), r.created_at))
    return hits[:limit], len(hits)


def _ref(r: Any) -> str:
    code = getattr(r, "public_code", None)
    if code:
        return code
    try:
        from app.api.public import public_code_for
        return public_code_for(r.id)
    except Exception:
        return r.id


def card(r: Any) -> Dict[str, Any]:
    text = (r.translations or {}).get("en") or r.ai_translation or r.summary or r.raw_text or ""
    return {
        "id": r.id,
        "ref": _ref(r),
        "type": r.type.value,
        "ward_id": r.ward_id,
        "ward_name": _wards().get(r.ward_id or "", {}).get("name_en"),
        "place_text": r.place_text,
        "people_count": r.people_count,
        "status": r.status.value,
        "urgency_score": r.urgency_score,
        "vulnerable": [v for v in VULNERABLE if getattr(r.vulnerable, v, False)],
        "summary": text[:160],
    }


def sentence(f: Dict[str, Any], total: int) -> str:
    """A plain first sentence: "4 critical cases are waiting."."""
    words = []
    if f.get("bands"):
        words.append(" or ".join(f["bands"]))
    if f.get("types"):
        words.append(" or ".join(f["types"]))
    noun = "case" if total == 1 else "cases"
    verb = "is" if total == 1 else "are"
    st = set(f.get("statuses") or [])
    if f.get("waiting_only"):
        tail = f"{verb} waiting"
    elif st and st <= set(STATUS_GROUPS["completed"]):
        tail = f"{verb} completed"
    elif st and st <= set(STATUS_GROUPS["dispatched"]):
        tail = f"{verb} dispatched"
    else:
        tail = "match"
        return f"{total} {' '.join(words + [noun])} {tail}."
    return f"{total} {' '.join(words + [noun])} {tail}."


def ask(question: str, requests: Iterable[Any], call=None) -> Dict[str, Any]:
    started = time.monotonic()
    filters, ai = gemini_filters(question, call=call)
    if filters is None:
        filters = rule_filters(question)
    t_parse = int((time.monotonic() - started) * 1000)
    t1 = time.monotonic()
    hits, total = run_filters(list(requests), filters)
    count_only = bool(re.search(r"\bhow many\b|\bcount\b|\bnumber of\b|\bkitne\b|\u0915\u093f\u0924\u0928\u0947", (question or "").lower()))
    t_search = int((time.monotonic() - t1) * 1000)
    shown = {k: v for k, v in filters.items() if k != "reason"}
    as_json = json.dumps(shown, ensure_ascii=False)
    from app.llm.providers import display_name

    trace = [
        {"agent": "Understand question", "status": "complete", "provider": ai["provider"], "model": ai.get("model"),
         "provider_label": display_name(ai["provider"]) if ai.get("model") else "Rules", "vendor": ai.get("vendor"),
         "latency_ms": ai.get("latency_ms") or t_parse, "tokens": ai.get("tokens"),
         "input": question, "output": as_json, "note": ai.get("fallback_reason")},
        {"agent": "Search cases (read-only)", "status": "complete", "provider": "tool", "model": None,
         "latency_ms": t_search, "tokens": None, "input": as_json, "output": f"{total} match(es)"},
    ]
    cases = [card(r) for r in hits]
    answer = _answer_with_refs(sentence(filters, total), cases)
    return {"question": question, "filters": shown, "reason": filters["reason"], "total": total,
            "count_only": count_only, "answer": answer,
            "cases": cases, "ai": ai, "trace": trace}


def _answer_with_refs(line: str, cases: List[Dict[str, Any]]) -> str:
    """Name only the cases this search returned, so the sentence cannot cite another id."""
    refs = []
    for row in cases:
        ref = str(row.get("ref") or "")
        if ref and ref not in refs:
            refs.append(ref)
    if not refs:
        return line
    return f"{line} Cases: {', '.join(refs)}."
