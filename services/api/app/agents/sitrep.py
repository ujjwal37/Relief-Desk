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
from app.tools.scoring import scoring_engine
from app.tools.storage import storage_service

logger = logging.getLogger("relief_desk.sitrep")

OPEN = {
    RequestStatus.NEW,
    RequestStatus.NEEDS_RECHECK,
    RequestStatus.MATCHED,
    RequestStatus.APPROVED,
}

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
  "brief": "4-8 sentences in English, grouped by triage tier, citing the given numbers",
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


def _open_cases() -> List[StoredRequest]:
    return [
        req
        for req in storage_service.list_requests()
        if req.status in OPEN and not req.merged_into
    ]


def _tier_of(req: StoredRequest) -> str:
    scored = scoring_engine.compute_urgency(req)
    return scored.tier or "standard"


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

    def free(kind: ResourceKind) -> int:
        return sum(
            1
            for res in storage_service.list_resources()
            if res.kind == kind
            and res.status == ResourceStatus.AVAILABLE
            and (res.capacity_remaining or 0) > 0
        )

    boats = free(ResourceKind.BOAT)
    medical = free(ResourceKind.MEDICAL)
    food = free(ResourceKind.FOOD)
    shelter = free(ResourceKind.SHELTER)
    boat_gap = max(0, rooftop - boats)
    gaps: List[str] = []
    if rooftop:
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
        f"{counts.pending} open cases by triage: {tiers}. "
        f"{counts.rescue_open} rescue, {counts.rooftop_like} rooftop/terrace. "
        f"{counts.free_boats} free boats, {counts.free_medical} medical, "
        f"{counts.free_food} food, {counts.free_shelter} shelter. {gap}. "
        f"A coordinator must approve every dispatch. Drafts only — nothing was sent."
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
            )
        drafted = validate(raw)
    except Exception as exc:
        logger.info("SITREP using template (%s)", exc)
        drafted = None
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
