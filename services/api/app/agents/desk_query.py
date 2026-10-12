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

TYPE_WORDS = {
    "rescue": ["rescue", "trapped", "stranded", "boat", "roof", "बचाव", "फंसे", "bachao", "phanse", "மீட்பு", "രക്ഷ"],
    "food": ["food", "water", "hungry", "खाना", "पानी", "khana", "paani", "உணவு", "ഭക്ഷണം"],
    "medical": ["medical", "medicine", "insulin", "doctor", "injured", "दवा", "dawai", "dawa", "मेडिकल", "மருந்து", "മരുന്ന്"],
    "shelter": ["shelter", "camp", "आश्रय", "आसरा", "முகாம்", "ക്യാമ്പ്"],
}
VULN_WORDS = {
    "elderly": ["elderly", "old", "senior", "aged", "बुजुर्ग", "बूढ़े", "buzurg", "bujurg", "budhe", "முதியோர்", "வயதான", "പ്രായമായ"],
    "child": ["child", "children", "kid", "baby", "infant", "बच्चे", "बच्चा", "bacche", "bachche", "குழந்தை", "കുട്ടി"],
    "pregnant": ["pregnant", "गर्भवती", "garbhvati", "கர்ப்பிணி", "ഗർഭിണി"],
    "disabled": ["disabled", "wheelchair", "विकलांग", "divyang", "மாற்றுத்திறனாளி"],
    "medical_need": ["dialysis", "oxygen", "bedridden"],
}
WAITING_WORDS = ["waiting", "still", "open", "pending", "unassigned", "not yet", "इंतज़ार", "इंतजार", "intezaar",
                 "intezar", "baaki", "बाकी", "காத்திருக்", "കാത്തിരി"]

FUNCTION = {
    "name": "search_cases",
    "description": "Read-only search over the relief desk's cases.",
    "parameters": {
        "type": "object",
        "properties": {
            "types": {"type": "array", "items": {"type": "string", "enum": TYPES}, "description": "Need types to include. Empty means any."},
            "ward_ids": {"type": "array", "items": {"type": "string"}, "description": "Ward ids such as ward_4. Empty means any ward."},
            "vulnerable": {"type": "array", "items": {"type": "string", "enum": VULNERABLE}, "description": "Only cases that include all of these groups."},
            "waiting_only": {"type": "boolean", "description": "True when the question asks for cases not yet dispatched or resolved."},
            "min_people": {"type": "integer", "description": "Only cases with at least this many people."},
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
        "The question may be in English, Hindi, Hinglish, Malayalam or Tamil. "
        "Map place names to ward ids, and a district name to all of its wards. Wards: "
        + ward_catalogue()
        + ". 'Waiting', 'still', 'pending' or 'not yet helped' means waiting_only=true. "
        "Only use filters the question asks for. Always call the function."
    )


def _has(text: str, words: Iterable[str]) -> bool:
    for w in words:
        if not w:
            continue
        if re.search(r"[a-z]", w):
            if re.search(rf"\b{re.escape(w)}", text):
                return True
        elif w in text:
            return True
    return False


def rule_filters(question: str) -> Dict[str, Any]:
    q = (question or "").lower()
    types = [t for t, words in TYPE_WORDS.items() if _has(q, words)]
    vulnerable = [v for v, words in VULN_WORDS.items() if _has(q, words)]
    ward_ids: List[str] = []
    for wid, w in _wards().items():
        names = [w["name_en"].lower(), (w.get("name_hi") or "").lower(), (w.get("district") or "").lower()]
        if _has(q, names):
            ward_ids.append(wid)
    m = re.search(r"(\d+)\s*(?:\+|or more|people|persons|log|लोग)", q)
    out: Dict[str, Any] = {
        "types": types,
        "ward_ids": ward_ids,
        "vulnerable": vulnerable,
        "waiting_only": _has(q, WAITING_WORDS),
        "min_people": int(m.group(1)) if m else None,
    }
    out["reason"] = describe(out)
    return out


def describe(f: Dict[str, Any]) -> str:
    parts = []
    if f.get("waiting_only"):
        parts.append("waiting")
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
        "types": [t for t in (raw.get("types") or []) if t in TYPES],
        "ward_ids": [w for w in (raw.get("ward_ids") or []) if w in wards],
        "vulnerable": [v for v in (raw.get("vulnerable") or []) if v in VULNERABLE],
        "waiting_only": bool(raw.get("waiting_only")),
        "min_people": None,
    }
    try:
        mp = int(raw["min_people"]) if raw.get("min_people") not in (None, "") else None
        out["min_people"] = mp if mp and mp > 0 else None
    except (TypeError, ValueError, KeyError):
        pass
    reason = str(raw.get("reason") or "").strip()
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


def gemini_filters(question: str, call=None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """One function call. Returns (filters or None, ai metadata). `call` is for tests."""
    from app.llm import client as llm

    c = llm.llm_client
    meta: Dict[str, Any] = {"provider": "fallback", "model": None, "latency_ms": 0, "tokens": None, "fallback_reason": None}
    if call is None and not c.gemini_live():
        meta["fallback_reason"] = "no_api_key"
        return None, meta
    if c.guard.circuit_open():
        meta["fallback_reason"] = "circuit_open"
        return None, meta
    key = c.cache_key("desk_query:" + system_prompt(), question.strip())
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
        fut = llm._GEMINI_POOL.submit(call, question, timeout_s)
        args, tokens = fut.result(timeout=timeout_s)
        c.guard.record_success()
    except Exception as exc:  # quota, timeout, SDK error: the rules answer instead
        c.guard.record_failure()
        text = str(exc)
        meta["fallback_reason"] = "quota" if ("429" in text or "RESOURCE_EXHAUSTED" in text) else (
            "timeout" if "Timeout" in type(exc).__name__ else "error")
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
        if f["min_people"] and (r.people_count or 0) < f["min_people"]:
            continue
        hits.append(r)
    hits.sort(key=lambda r: (-(r.urgency_score or 0), r.created_at))
    return hits[:limit], len(hits)


def card(r: Any) -> Dict[str, Any]:
    text = (r.translations or {}).get("en") or r.ai_translation or r.summary or r.raw_text or ""
    return {
        "id": r.id,
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


def ask(question: str, requests: Iterable[Any], call=None) -> Dict[str, Any]:
    started = time.monotonic()
    filters, ai = gemini_filters(question, call=call)
    if filters is None:
        filters = rule_filters(question)
    t_parse = int((time.monotonic() - started) * 1000)
    t1 = time.monotonic()
    hits, total = run_filters(list(requests), filters)
    t_search = int((time.monotonic() - t1) * 1000)
    shown = {k: v for k, v in filters.items() if k != "reason"}
    as_json = json.dumps(shown, ensure_ascii=False)
    trace = [
        {"agent": "Understand question", "status": "complete", "provider": ai["provider"], "model": ai.get("model"),
         "latency_ms": ai.get("latency_ms") or t_parse, "tokens": ai.get("tokens"),
         "input": question, "output": as_json, "note": ai.get("fallback_reason")},
        {"agent": "Search cases (read-only)", "status": "complete", "provider": "tool", "model": None,
         "latency_ms": t_search, "tokens": None, "input": as_json, "output": f"{total} match(es)"},
    ]
    return {"question": question, "filters": shown, "reason": filters["reason"], "total": total,
            "cases": [card(r) for r in hits], "ai": ai, "trace": trace}
