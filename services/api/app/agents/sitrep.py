"""Situation brief from live in-memory counts. Gemini drafts wording; numbers stay deterministic."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.llm.adk_runtime import ai_step
from app.llm.client import llm_client
from app.models.firestore_models import RequestStatus, ResourceKind, ResourceStatus, StoredRequest
from app.models.schemas import AiCall, IncidentType
from app.tools.storage import storage_service

logger = logging.getLogger("relief_desk.sitrep")

OPEN = {
    RequestStatus.NEW,
    RequestStatus.NEEDS_RECHECK,
    RequestStatus.MATCHED,
    RequestStatus.APPROVED,
}

WAITING = {RequestStatus.NEW, RequestStatus.NEEDS_RECHECK, RequestStatus.MATCHED}

_cache_lock = threading.Lock()
_cache: Dict[str, "SitrepResponse"] = {}
_last_at = 0.0
CACHE_SECONDS = 120.0


class SitrepCounts(BaseModel):
    pending: int
    by_tier: Dict[str, int]
    rescue_open: int
    rooftop_like: int
    free_boats: int
    busy_boats: int = 0
    busy_medical: int = 0
    free_medical: int
    free_food: int
    free_shelter: int
    boat_gap: int
    gaps: List[str]


class SitrepDrafts(BaseModel):
    sms_en: str
    sms_hi: str
    sms_ml: str
    whatsapp_en: str
    whatsapp_hi: str
    whatsapp_ml: str


class SitrepResponse(BaseModel):
    brief: str
    counts: SitrepCounts
    drafts: SitrepDrafts
    ai: AiCall
    cached: bool = False
    send: bool = False


SYSTEM = """You write a coordinator situation brief for a Kerala flood desk.
Use ONLY the numbers in the JSON. Do not invent counts, places, or forecasts.
Output one JSON object:
{
  "brief": "exactly 3 short lines joined by \\n, under 240 characters in total: 1) pending total with Critical (immediate), Urgent and Can wait (standard) counts; 2) free boat teams for open rescue cases, and free medical teams; 3) the first gap from gaps, or No resource gap",
  "sms_en": "one SMS under 300 characters",
  "sms_hi": "same SMS in Hindi Devanagari",
  "sms_ml": "same SMS in Malayalam",
  "whatsapp_en": "one WhatsApp draft under 500 characters",
  "whatsapp_hi": "same WhatsApp in Hindi",
  "whatsapp_ml": "same WhatsApp in Malayalam"
}
These are drafts only. Never claim a message was sent. No medical or legal advice.
"""


class _SitrepModel(BaseModel):
    brief: str = Field(min_length=10, max_length=4000)
    sms_en: str = Field(min_length=8, max_length=400)
    sms_hi: str = Field(min_length=8, max_length=400)
    sms_ml: str = Field(min_length=8, max_length=400)
    whatsapp_en: str = Field(min_length=8, max_length=700)
    whatsapp_hi: str = Field(min_length=8, max_length=700)
    whatsapp_ml: str = Field(min_length=8, max_length=700)


from app.tools.desk_counts import is_free_team, is_waiting  # noqa: E402


def _open_cases() -> List[StoredRequest]:
    return [
        req
        for req in storage_service.list_requests()
        # Same "waiting" as the Command queue: not sent, not closed as information, not a dismissed hoax.
        if is_waiting(req)
    ]


def _tier_of(req: StoredRequest) -> str:
    # Same bands as the queue and Ask the desk: score 80+ Critical, 60+ Urgent, else Can wait.
    if (req.urgency_score or 0) >= 80:
        return "immediate"
    if (req.urgency_score or 0) >= 60:
        return "urgent"
    return "standard"


def _rooftop_like(req: StoredRequest) -> bool:
    text = " ".join(
        part
        for part in (req.raw_text, req.summary, req.place_text, req.urgency_reason)
        if part
    ).lower()
    words = ("roof", "terrace", "chat", "chhat", "छत", "മുകളിൽ")
    return req.type == IncidentType.RESCUE and any(word in text for word in words)


def collect_counts() -> SitrepCounts:
    cases = _open_cases()
    by_tier = {"immediate": 0, "urgent": 0, "standard": 0}
    rescue = 0
    rooftop = 0
    for req in cases:
        tier = _tier_of(req)
        by_tier[tier] = by_tier.get(tier, 0) + 1
        if req.type == IncidentType.RESCUE:
            rescue += 1
        if _rooftop_like(req):
            rooftop += 1

    def is_free(res) -> bool:
        return is_free_team(res)

    def is_busy(res) -> bool:
        return bool(res.assigned_request_id) or res.status != ResourceStatus.AVAILABLE or (res.capacity_remaining or 0) <= 0

    def free(kind: ResourceKind) -> int:
        return sum(1 for res in storage_service.list_resources() if res.kind == kind and is_free(res))

    def busy(kind: ResourceKind) -> int:
        return sum(1 for res in storage_service.list_resources() if res.kind == kind and is_busy(res))

    boats = free(ResourceKind.BOAT)
    medical = free(ResourceKind.MEDICAL)
    food = free(ResourceKind.FOOD)
    shelter = free(ResourceKind.SHELTER)
    boat_gap = max(0, rooftop - boats)
    gaps: List[str] = []
    if rooftop and boat_gap:
        gaps.append(
            f"{rooftop} rooftop/terrace rescue cases, {boats} free boat team(s), gap {boat_gap}"
        )
    if rescue and boats == 0:
        gaps.append(f"{rescue} open rescue cases and 0 free boats")
    medical_need = sum(1 for req in cases if req.type == IncidentType.MEDICAL)
    if medical_need > medical:
        gaps.append(f"{medical_need} open medical cases, {medical} free medical team(s)")
    food_need = sum(1 for req in cases if req.type == IncidentType.FOOD)
    if food_need > food:
        gaps.append(f"{food_need} open food cases, {food} free food team(s)")
    return SitrepCounts(
        pending=len(cases),
        by_tier=by_tier,
        rescue_open=rescue,
        rooftop_like=rooftop,
        free_boats=boats,
        busy_boats=busy(ResourceKind.BOAT),
        busy_medical=busy(ResourceKind.MEDICAL),
        free_medical=medical,
        free_food=food,
        free_shelter=shelter,
        boat_gap=boat_gap,
        gaps=gaps,
    )


def _template_brief(counts: SitrepCounts) -> _SitrepModel:
    immediate = counts.by_tier.get("immediate", 0)
    urgent = counts.by_tier.get("urgent", 0)
    standard = counts.by_tier.get("standard", 0)
    tiers = f"Immediate {immediate}, Urgent {urgent}, Standard {standard}"
    gap = counts.gaps[0] if counts.gaps else "No resource gap from current open counts"
    brief = (
        f"{counts.pending} open: {immediate} Critical, {urgent} Urgent, {standard} Can wait.\n"
        f"Boats: {counts.free_boats} free, {counts.busy_boats} busy · Medical: {counts.free_medical} free, {counts.busy_medical} busy.\n"
        f"Nothing is sent without a coordinator."
    )
    sms = (
        f"Relief Desk draft: {counts.pending} pending (now {immediate}). "
        f"{gap}. Call 112 in an emergency."
    )
    return _SitrepModel(
        brief=brief,
        sms_en=sms,
        sms_hi=f"रिलीफ डेस्क ड्राफ्ट: {counts.pending} लंबित मामले। {gap}। आपात में 112।",
        sms_ml=f"റിലീഫ് ഡെസ്ക് ഡ്രാഫ്റ്റ്: {counts.pending} തീർപ്പാക്കാത്ത കേസുകൾ. {gap}. അടിയന്തരത്തിൽ 112.",
        whatsapp_en=f"{brief} WhatsApp draft only.",
        whatsapp_hi=f"व्हाट्सऐप ड्राफ्ट: {counts.pending} लंबित। {gap}। भेजा नहीं गया।",
        whatsapp_ml=f"വാട്ട്സ്ആപ്പ് ഡ്രാഫ്റ്റ്: {counts.pending} തീർപ്പാക്കാത്തത്. {gap}. അയച്ചിട്ടില്ല.",
    )


def _numbers_ok(text: str, counts: SitrepCounts) -> bool:
    allowed = {
        counts.pending,
        counts.rescue_open,
        counts.rooftop_like,
        counts.free_boats,
        counts.busy_boats,
        counts.busy_medical,
        counts.free_medical,
        counts.free_food,
        counts.free_shelter,
        counts.boat_gap,
        *counts.by_tier.values(),
        112,
        0,
    }
    for token in re.findall(r"\b\d+\b", text or ""):
        if int(token) not in allowed:
            return False
    return True


def generate_sitrep() -> SitrepResponse:
    global _last_at
    counts = collect_counts()
    key = hashlib.sha256(json.dumps(counts.model_dump(), sort_keys=True).encode()).hexdigest()
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (now - _last_at) < CACHE_SECONDS:
            return hit.model_copy(update={"cached": True})

    def validate(raw: str) -> _SitrepModel:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.strip("`")
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _SitrepModel.model_validate_json(clean.strip())
        lines = [line for line in parsed.brief.splitlines() if line.strip()]
        if len(lines) > 3 or len(parsed.brief) > 300:
            raise ValueError("sitrep brief longer than 3 lines")
        blob = " ".join(parsed.model_dump().values())
        if not _numbers_ok(blob, counts):
            raise ValueError("sitrep invented a number")
        return parsed

    drafted: Optional[_SitrepModel] = None
    try:
        with ai_step("Sitrep"):
            raw = llm_client.generate_content(
                SYSTEM,
                f"<counts>\n{json.dumps(counts.model_dump(), ensure_ascii=False)}\n</counts>",
                validator=validate,
                max_retries=1,
                max_output_tokens=700,
            )
        drafted = validate(raw)
    except Exception as exc:
        logger.info("SITREP using template (%s)", exc)
        drafted = None
    finally:
        llm_client._tls.max_output_tokens = None
    ai = llm_client.last_ai.model_copy()
    if drafted is None or ai.provider == "fallback":
        drafted = _template_brief(counts)
        if ai.provider != "fallback":
            ai = AiCall(provider="fallback", fallback_reason="sitrep_template")
    result = SitrepResponse(
        brief=drafted.brief,
        counts=counts,
        drafts=SitrepDrafts(
            sms_en=drafted.sms_en,
            sms_hi=drafted.sms_hi,
            sms_ml=drafted.sms_ml,
            whatsapp_en=drafted.whatsapp_en,
            whatsapp_hi=drafted.whatsapp_hi,
            whatsapp_ml=drafted.whatsapp_ml,
        ),
        ai=ai,
        cached=False,
        send=False,
    )
    with _cache_lock:
        _cache[key] = result
        _last_at = now
    return result


_warming = threading.Event()


def _warm_in_background() -> None:
    try:
        generate_sitrep()
    except Exception:
        logger.info("SITREP background draft failed")
    finally:
        _warming.clear()


def generate_sitrep_fast() -> SitrepResponse:
    """Never keep the coordinator waiting on a slow model call.

    A cached AI brief for the current counts is returned at once. Otherwise the honest
    rules summary (built only from the live counts) comes back immediately, labelled as
    rules, while the AI draft is written in the background for the next refresh.
    """
    counts = collect_counts()
    key = hashlib.sha256(json.dumps(counts.model_dump(), sort_keys=True).encode()).hexdigest()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (time.monotonic() - _last_at) < CACHE_SECONDS:
            return hit.model_copy(update={"cached": True})
    if not _warming.is_set():
        _warming.set()
        threading.Thread(target=_warm_in_background, daemon=True).start()
    drafted = _template_brief(counts)
    return SitrepResponse(
        brief=drafted.brief,
        counts=counts,
        drafts=SitrepDrafts(
            sms_en=drafted.sms_en, sms_hi=drafted.sms_hi, sms_ml=drafted.sms_ml,
            whatsapp_en=drafted.whatsapp_en, whatsapp_hi=drafted.whatsapp_hi, whatsapp_ml=drafted.whatsapp_ml,
        ),
        ai=AiCall(provider="fallback", fallback_reason="sitrep_warming"),
        cached=False,
        send=False,
    )


def prewarm_sitrep() -> None:
    """Fill the 120s cache so the first SITREP click is not an 18s Gemini wait."""
    try:
        generate_sitrep()
    except Exception:
        logger.info("SITREP prewarm skipped")
