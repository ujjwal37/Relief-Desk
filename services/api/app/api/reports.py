import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from app.agents.chat_intake import chat_intake_agent, ChatTurnResponse, ConfirmationCardData
from app.agents.intake import extract_with_rules, intake_agent
from app.llm.ai_queue import ai_priority, report_priority
from app.agents.dedupe import dedupe_agent
from app.tools.storage import storage_service
from app.tools.scoring import scoring_engine
from app.tools.ratelimit import rate_limiter
from app.tools.asr import asr_service, VoiceNoteMetadata, ASRResult
from app.tools.translation import translation_service, TranslationResult
from app.models.firestore_models import PossibleDuplicate, ReportQuote, StoredReport, StoredRequest, RequestStatus
from app.models.schemas import ExtractedRequest, HazardType, IncidentType
from app.tools.request_contract import canonical_request_dict
from app.agents.summary import guard_summary, summary_from_report
from app.tools.nlu_rules import extract_place, people_bounds, people_count, place_is_usable, vulnerable_flags
from app.agents.dedupe import confidence_phrase
from app.tools.trust import detect_hoax_or_flood, hoax_reason_for
from app.tools.gazetteer import gazetteer
from app.llm.client import llm_client

logger = logging.getLogger("relief_desk.reports")

router = APIRouter(prefix="/api", tags=["Reports & Intake"])


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    scenario_id: str = "flood"
    language: Optional[str] = None
    location_pin: Optional[Dict[str, float]] = None


class StructuredReportFacts(BaseModel):
    """Facts confirmed on the shared card. Chat and form both send this shape."""
    incident_type: Optional[str] = None
    place_text: Optional[str] = None
    people_count: Optional[int] = None
    vulnerable: Optional[Dict[str, bool]] = None
    hazard: Optional[str] = None
    summary: Optional[str] = None


class ReportSubmitRequest(BaseModel):
    text: Optional[str] = ""
    channel: str = "text"  # "text" | "voice"
    lang: str = "en"
    source_id: str = "anon_device"
    location_pin: Optional[Dict[str, float]] = None
    scenario_id: str = "flood"
    voice_note_id: Optional[str] = None
    audio_base64: Optional[str] = None
    image_base64: Optional[str] = None
    mime_type: Optional[str] = None
    structured: Optional[StructuredReportFacts] = None
    idempotency_key: Optional[str] = None
    raw_text: Optional[str] = None


class ReportSubmitResponse(BaseModel):
    report_id: str
    request_id: str
    status_token: str
    summary: str
    urgency_score: float
    dedupe_decision: str
    flags: List[str]
    safety_line: str
    transcript: Optional[str] = None
    asr_confidence: Optional[float] = None


@router.post("/intake/chat", response_model=ChatTurnResponse)
def handle_chat_turn(payload: ChatMessageRequest):
    return chat_intake_agent.process_turn(
        session_id=payload.session_id,
        user_message=payload.message,
        scenario_id=payload.scenario_id,
        lang_override=payload.language,
        location_pin=payload.location_pin
    )


@router.get("/voice/notes", response_model=List[VoiceNoteMetadata])
def get_synthetic_voice_notes():
    """Returns catalog of pre-recorded synthetic voice notes for demo audio submission."""
    return asr_service.list_voice_notes()


def _submit_report_impl(payload: ReportSubmitRequest) -> ReportSubmitResponse:
    # Retries from the phone queue send the same key and must not create a second case.
    replay = _replay_idempotent(payload.idempotency_key)
    if replay is not None:
        return replay

    # 0. ASR. A catalog note is local. Live audio is the only path that can call a model here.
    transcript: Optional[str] = None
    asr_confidence: Optional[float] = None
    report_text: str = payload.text or ""

    media_bytes = None
    media_mime = None
    if payload.image_base64:
        import base64

        try:
            media_bytes = base64.b64decode(payload.image_base64, validate=True)
            from app.tools.images import jpeg_downscale

            media_bytes = jpeg_downscale(media_bytes)
            media_mime = "image/jpeg"
            payload.channel = "photo" if payload.channel == "text" else payload.channel
        except Exception:
            media_bytes = None
    if payload.channel == "voice" or payload.voice_note_id or payload.audio_base64:
        asr_res = asr_service.transcribe(
            voice_note_id=payload.voice_note_id,
            audio_base64=payload.audio_base64,
            lang_hint=payload.lang
        )
        transcript = asr_res.transcript
        asr_confidence = asr_res.asr_confidence
        if payload.channel == "voice" and transcript:
            report_text = transcript
        elif not report_text.strip():
            report_text = transcript
        if payload.audio_base64 and media_bytes is None:
            import base64

            try:
                media_bytes = base64.b64decode(payload.audio_base64, validate=True)
                media_mime = "audio/wav"
            except Exception:
                media_bytes = None
        if payload.voice_note_id and media_bytes is None:
            from pathlib import Path

            wav = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "voice" / f"{payload.voice_note_id}.wav"
            if wav.exists():
                media_bytes = wav.read_bytes()
                media_mime = "audio/wav"

    demo_sample = (payload.source_id or "").startswith("demo_sample_")
    # 1. Rate limiting check (flags only, never deletes). Demo sample buttons may be clicked again.
    if demo_sample:
        flags: List[str] = []
    else:
        is_limited, _ = rate_limiter.check_and_record(payload.source_id)
        flags = ["rate_limited"] if is_limited else []

    # 2. Store raw report immediately with generated status token and audio transcript
    status_token = f"tok_{uuid.uuid4().hex[:12]}"
    raw_report = storage_service.save_report_raw(
        raw_text=report_text,
        channel=payload.channel,
        lang=payload.lang,
        source_id=payload.source_id,
        trust_level="anonymous",
        pack_id=payload.scenario_id,
        flags=flags,
        status_token=status_token,
        transcript=transcript,
        asr_confidence=asr_confidence,
    )

    # Citizen words stay the raw report. Voice uses the live transcript, not a stored caption.
    if payload.channel == "voice" and transcript:
        citizen_text = transcript.strip()
        report_text = citizen_text
    else:
        citizen_text = (payload.raw_text or payload.text or report_text or "").strip()
        if payload.channel == "photo" and not citizen_text:
            citizen_text = "Flood photo"
        if citizen_text:
            report_text = citizen_text

    hoax_blob = _hoax_blob(payload, citizen_text or report_text)
    hoax_reason = None if demo_sample else hoax_reason_for(hoax_blob)
    if not demo_sample:
        for flag in detect_hoax_or_flood(
            storage_service.list_reports(),
            hoax_blob,
            payload.source_id,
        ):
            if flag not in flags:
                flags.append(flag)
        if hoax_reason:
            for flag in ("hoax", "likely_hoax"):
                if flag not in flags:
                    flags.append(flag)

    # Rule-based type, place, and people. The status page can show tips before any model call.
    extracted = extract_with_rules(report_text)
    if payload.channel == "photo" and extracted.type == IncidentType.OTHER:
        extracted.type = IncidentType.RESCUE
        extracted.hazard = HazardType.WATER_RISING
    machine_summary = _apply_card(extracted, payload, report_text)
    pin_lat, pin_lng, ward_id = _pin_for(payload, extracted, report_text)
    req_id = f"req_{uuid.uuid4().hex[:10]}"
    req_obj = StoredRequest(
        id=req_id,
        event_id="event_kerala_flood",
        pack_id=payload.scenario_id,
        type=extracted.type,
        picked_type=(payload.structured.incident_type if payload.structured else None),
        place_text=extracted.place_text or (payload.location_pin.get("ward") if payload.location_pin else "") or "",
        ward_id=ward_id,
        lat=pin_lat,
        lng=pin_lng,
        people_count=_stated_people(extracted.people.count, citizen_text or report_text),
        people_span=(people_bounds(citizen_text or report_text) or (None, None, None))[2],
        vulnerable=extracted.vulnerable,
        hazard=extracted.hazard,
        status=RequestStatus.NEW,
        flags=list(flags),
        hoax_reason=hoax_reason,
        raw_text=citizen_text or report_text,
        summary=machine_summary,
        analysis_status="analysing",
    )
    _remember_words(req_obj, raw_report.id, citizen_text or report_text)
    urgency_res = scoring_engine.compute_urgency(req_obj)
    req_obj.urgency_score = urgency_res.score
    req_obj.urgency_reason = urgency_res.reason
    storage_service.save_request(req_obj, actor="intake_pipeline")
    _link_report(raw_report, req_obj, req_id, machine_summary, citizen_text or report_text)

    from app.agents.pipeline import mark_analysing, spawn
    mark_analysing(req_id, channel=payload.channel or "text")

    provisional = _response_for(raw_report, req_obj, "new", flags, transcript, asr_confidence)
    storage_service.save_idempotent(payload.idempotency_key, provisional.model_dump())
    finished: Dict[str, ReportSubmitResponse] = {}

    def job() -> None:
        from app.llm.pacer import forbid_replay, set_pace
        source = payload.source_id or ""
        pace = source == "judge_input" or source.startswith("live_demo_")
        if pace:
            set_pace(True)
        if source == "judge_input":
            forbid_replay(True)
        try:
            finished["response"] = _enrich_report(
                payload, req_id, raw_report.id, report_text, citizen_text, flags, transcript, asr_confidence,
                media_bytes, media_mime,
            )
        except Exception:
            logger.exception("Background intake failed for %s", req_id)
            _mark_failed(req_id)
            finished["response"] = provisional
        finally:
            if pace:
                set_pace(False)
            if source == "judge_input":
                forbid_replay(False)

    # Tests run this inline, so the body they read is the finished case.
    # Production returns the provisional ids and lets the thread emit case.updated.
    spawn(job)
    final = finished.get("response", provisional)
    storage_service.save_idempotent(payload.idempotency_key, final.model_dump())
    return final


@router.post("/reports", response_model=ReportSubmitResponse)
def submit_report(payload: ReportSubmitRequest, request: Request = None):
    if (payload.source_id or "") == "judge_input":
        from app.llm.pacer import LIMIT_MESSAGE, judge_limit
        ip = "local"
        if request is not None and request.client is not None:
            ip = request.client.host or "local"
        if not judge_limit.allow(ip) or not llm_client.gemini_live():
            raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
    try:
        return _submit_report_impl(payload)
    except HTTPException:
        raise
    except Exception:
        storage_service.release_idempotent(payload.idempotency_key)
        raise


def _apply_card(extracted: ExtractedRequest, payload: ReportSubmitRequest, report_text: str) -> Optional[str]:
    """Confirmed card facts win. A sentence-length card place is the old bad parse."""
    if not payload.structured:
        return None
    facts = payload.structured
    canon = canonical_request_dict(
        incident_type=facts.incident_type or extracted.type.value,
        place_text=facts.place_text if facts.place_text is not None else extracted.place_text,
        people_count=facts.people_count if facts.people_count is not None else extracted.people.count,
        vulnerable=facts.vulnerable if facts.vulnerable is not None else extracted.vulnerable.model_dump(),
        hazard=facts.hazard or extracted.hazard.value,
        summary=facts.summary or report_text,
        lang=payload.lang,
        scenario_id=payload.scenario_id,
        lat=payload.location_pin.get("lat") if payload.location_pin else None,
        lng=payload.location_pin.get("lng") if payload.location_pin else None,
    )
    extracted.type = IncidentType(canon["type"])
    extracted.place_text = canon["place_text"]
    extracted.people.count = canon["people_count"]
    extracted.people.confidence = 1.0
    extracted.hazard = HazardType(canon["hazard"])
    heard = vulnerable_flags(report_text)
    for flag, value in canon["vulnerable"].items():
        setattr(extracted.vulnerable, flag, bool(value or heard.get(flag)))
    card_place = (facts.place_text or "").strip()
    if not place_is_usable(card_place):
        card_place = ""
    if not place_is_usable(extracted.place_text):
        extracted.place_text = None
    ruled = extract_place(report_text)
    weak = (
        not card_place
        or "auto-detected" in card_place.lower()
        or len(card_place) > 60
        or card_place.count(" ") > 8
    )
    if ruled and weak:
        extracted.place_text = ruled
    elif card_place and not weak:
        extracted.place_text = card_place
    stated = people_count(report_text)
    if extracted.people.count == 0 or (extracted.people.count is not None and extracted.people.count <= 0):
        extracted.people.count = stated if stated else None
    elif facts.people_count == 0 and stated != 0:
        extracted.people.count = stated
    summary = canon["summary"] if facts.summary else None
    if summary and "person(s) needing " in summary:
        return None
    if not summary:
        return None
    return summary_from_report(report_text, summary)


def _hoax_blob(payload: ReportSubmitRequest, report_text: str) -> str:
    """Hoax phrases can sit in the original message while the card summary is only the last reply."""
    parts = [report_text or ""]
    if payload.structured and payload.structured.summary:
        parts.append(payload.structured.summary)
    if payload.raw_text:
        parts.append(payload.raw_text)
    if payload.text:
        parts.append(payload.text)
    return "\n".join(part for part in parts if part)


def _stated_people(count: Optional[int], report_text: str) -> Optional[int]:
    """Unknown stays null. A card that says 0 is not a headcount the citizen gave."""
    bounds = people_bounds(report_text)
    stated = bounds[1] if bounds else None
    if count is None or count <= 0:
        return stated if stated else None
    return count


def _pin_for(payload: ReportSubmitRequest, extracted: ExtractedRequest, report_text: str) -> Tuple[float, float, Optional[str]]:
    # No pin and no confident place: store no location rather than a made-up default pin.
    pin_lat = payload.location_pin.get("lat") if payload.location_pin else None
    pin_lng = payload.location_pin.get("lng") if payload.location_pin else None
    ward_id = _resolve_ward_id(extracted.place_text, report_text)
    geo = gazetteer.lookup(extracted.place_text or report_text or "")
    if not payload.location_pin and geo.lat is not None and geo.lng is not None and not geo.is_low_confidence:
        pin_lat, pin_lng = geo.lat, geo.lng
    return pin_lat, pin_lng, ward_id


def _link_report(
    raw_report: StoredReport,
    req_obj: StoredRequest,
    req_id: str,
    machine_summary: Optional[str],
    report_text: str,
) -> None:
    if raw_report.request_id is None:
        raw_report.request_id = req_id
    raw_report.case_id = raw_report.request_id
    raw_report.joined_existing = raw_report.case_id != req_id
    raw_report.incident_type = req_obj.type.value
    raw_report.place_text = req_obj.place_text
    raw_report.ward_id = req_obj.ward_id
    summary = (machine_summary or report_text or "").strip().replace("\n", " ")
    raw_report.summary = summary[:160]


def _response_for(
    raw_report: StoredReport,
    req_obj: StoredRequest,
    decision: str,
    flags: List[str],
    transcript: Optional[str],
    asr_confidence: Optional[float],
) -> ReportSubmitResponse:
    reading = req_obj.analysis_status == "analysing" and not (req_obj.ai_translation or "").strip()
    return ReportSubmitResponse(
        report_id=raw_report.id,
        request_id=req_obj.id,
        status_token=raw_report.status_token or "",
        summary="" if reading else (req_obj.ai_translation or req_obj.summary or ""),
        urgency_score=req_obj.urgency_score,
        dedupe_decision=decision,
        flags=list(flags),
        safety_line="In an immediate emergency call 112.",
        transcript=transcript,
        asr_confidence=asr_confidence,
    )


def _enrich_report(
    payload: ReportSubmitRequest,
    req_id: str,
    report_id: str,
    report_text: str,
    citizen_text: str,
    flags: List[str],
    transcript: Optional[str],
    asr_confidence: Optional[float],
    media_bytes: Optional[bytes] = None,
    media_mime: Optional[str] = None,
) -> ReportSubmitResponse:
    """Duplicate check first, from rules and embeddings, so a merge shows in seconds.

    Then one model call (facts, type, translations) waits its turn in the priority queue
    and refines the case. Each save emits case.updated or case.merged.
    """
    from app.agents.pipeline import finish
    from app.llm.pacer import forbid_replay, set_pace

    source = payload.source_id or ""
    pace = source == "judge_input" or source.startswith("live_demo_")
    if pace:
        set_pace(True)
    if source == "judge_input":
        forbid_replay(True)

    req_obj = storage_service.get_request(req_id)
    raw_report = storage_service.get_report(report_id)
    if req_obj is None or raw_report is None:
        raise RuntimeError("report disappeared before enrichment")

    ruled = extract_with_rules(report_text)
    _apply_card(ruled, payload, report_text)
    bounds = people_bounds(citizen_text or report_text)
    if bounds and (req_obj.people_count or 0) < bounds[1]:
        req_obj.people_count = bounds[1]
    decision = _dedupe_and_rank(req_obj, ruled, payload.text or report_text, payload.source_id)

    if req_obj.merged_into:
        # The case it joined already carries the facts. A merged report does not take a model slot.
        target = storage_service.get_request(req_obj.merged_into)
        if target is not None and target.analysis_status != "analysing":
            finish(target.id)
        finish(req_id)
        stored = storage_service.get_request(req_id) or req_obj
        return _response_for(raw_report, stored, decision.decision.value, flags, transcript, asr_confidence)

    refined = _refine_with_model(payload, req_id, report_id, report_text, citizen_text, flags, media_bytes, media_mime)
    if refined is not None:
        decision = refined
    stored = storage_service.get_request(req_id) or req_obj
    return _response_for(raw_report, stored, decision.decision.value, flags, transcript, asr_confidence)


_dedupe_lock = threading.Lock()


def _dedupe_and_rank(req_obj: StoredRequest, extracted: ExtractedRequest, words: str, source_id: str = ""):
    """No model call. A newer report joins an older case, never the other way round."""
    from app.agents.matching import matching_agent
    from app.agents.pipeline import note_dedupe

    with _dedupe_lock:
        mine = req_obj.created_at or ""
        existing = [
            row for row in storage_service.list_requests()
            if row.id != req_obj.id and not row.merged_into and (row.created_at or "") <= mine
        ]
        candidates = dedupe_agent.prefilter_candidates(
            new_req=extracted,
            new_lat=req_obj.lat,
            new_lng=req_obj.lng,
            new_ward=req_obj.ward_id,
            existing_requests=existing,
        )
        decision = dedupe_agent.evaluate(
            words,
            extracted,
            candidates,
            new_lat=req_obj.lat,
            new_lng=req_obj.lng,
            judge=False,
        )
        _apply_dedupe(req_obj, decision, source_id)
        if not req_obj.merged_into and req_obj.analysis_status == "analysing":
            note_dedupe(req_obj)
            storage_service.save_request(req_obj, actor="dedupe_agent")
    ranked = storage_service.get_request(req_obj.merged_into or req_obj.id) or req_obj
    matching_agent.find_matches(ranked, top_n=3)
    return decision


def _translation_for(report_text: str, analysis: ExtractedRequest, ai_usage) -> TranslationResult:
    text_en = getattr(analysis, "text_en", None)
    if text_en and ai_usage.provider != "fallback":
        from app.llm.providers import TEST_PROVIDERS

        return translation_service.from_model(
            report_text, text_en, getattr(analysis, "text_hi", None), getattr(analysis, "translation_confidence", None),
            persist=ai_usage.provider not in TEST_PROVIDERS,
        )
    return translation_service.translate_report(report_text, allow_model=False)


def _refine_with_model(
    payload: ReportSubmitRequest,
    req_id: str,
    report_id: str,
    report_text: str,
    citizen_text: str,
    flags: List[str],
    media_bytes: Optional[bytes] = None,
    media_mime: Optional[str] = None,
):
    """The one model call for this report. Critical cases get a slot first."""
    from app.agents.matching import matching_agent
    from app.agents.pipeline import finish

    waiting = storage_service.get_request(req_id)
    with ai_priority(report_priority(waiting.urgency_score if waiting else 0)):
        if media_bytes and media_mime and payload.channel == "photo":
            analysis = intake_agent.parse_media_report(
                report_text, media_bytes, media_mime, language_hint=payload.lang
            )
        elif payload.channel == "voice" and (citizen_text or report_text):
            analysis = intake_agent.parse_report(citizen_text or report_text, language_hint=payload.lang)
        elif media_bytes and media_mime:
            analysis = intake_agent.parse_media_report(
                report_text, media_bytes, media_mime, language_hint=payload.lang
            )
        else:
            analysis = intake_agent.parse_report(report_text, language_hint=payload.lang)
        ai_usage = llm_client.last_ai.model_copy()
    trans_res = _translation_for(report_text, analysis, ai_usage)
    if (payload.source_id or "") == "judge_input" and ai_usage.provider == "cache":
        ai_usage.provider = "fallback"
        ai_usage.cached = False
        ai_usage.fallback_reason = "judge_no_replay"
    ai_source = {"gemini": "gemini", "cache": "recorded", "antigravity-local": "antigravity-local",
                 "openai_compat": "openai_compat"}.get(
        ai_usage.provider, "offline_fallback"
    )
    model_reason = (getattr(analysis, "hoax_reason", None) or "").strip()
    if getattr(analysis, "likely_hoax", False) or model_reason:
        for flag in ("hoax", "likely_hoax"):
            if flag not in flags:
                flags.append(flag)
    machine_summary = _apply_card(analysis, payload, report_text)
    if trans_res.is_low_confidence and "low_translation_confidence" not in flags:
        flags.append("low_translation_confidence")
        flags.append("needs_human_review")

    req_obj = storage_service.get_request(req_id)
    raw_report = storage_service.get_report(report_id)
    if req_obj is None or raw_report is None:
        raise RuntimeError("report disappeared before enrichment")

    before = (req_obj.type, req_obj.place_text, req_obj.ward_id)
    joined = (req_obj.merged_count or 1) > 1
    pin_lat, pin_lng, ward_id = _pin_for(payload, analysis, report_text)
    req_obj.type = analysis.type
    chosen_place = analysis.place_text or req_obj.place_text
    if not place_is_usable(chosen_place):
        chosen_place = extract_place(citizen_text or report_text)
    req_obj.place_text = chosen_place if place_is_usable(chosen_place) else ""
    req_obj.ward_id = ward_id
    req_obj.lat = pin_lat
    req_obj.lng = pin_lng
    # Unknown stays unknown (None): never invent a count of 1.
    counted = analysis.people.count or req_obj.people_count or None
    bounds = people_bounds(citizen_text or report_text)
    if bounds and (counted or 0) < bounds[1]:
        counted = bounds[1]
    # Reports that joined while the model worked may carry a larger count. Keep the largest.
    req_obj.people_count = (max(counted or 0, req_obj.people_count or 0) or None) if joined else counted
    if joined:
        for name, value in analysis.vulnerable.model_dump().items():
            if value:
                setattr(req_obj.vulnerable, name, True)
    else:
        req_obj.vulnerable = analysis.vulnerable
    req_obj.hazard = analysis.hazard
    from app.agents.depth import validate_depth
    depth = validate_depth(getattr(analysis, "water_depth", None), getattr(analysis, "water_depth_quote", None), citizen_text or report_text, ai_source)
    if not depth or depth.get("band") == "unknown":
        from app.agents.depth import depth_from_text
        depth = depth_from_text(citizen_text or report_text) or depth
    if depth is not None or not joined:
        req_obj.water_depth = depth
    flags = set(flags)
    # Two readings of the head count disagree: keep the larger, mark it provisional for the coordinator.
    model_count = analysis.people.count
    if model_count and bounds and not (bounds[0] <= model_count <= bounds[1]):
        flags.add("count_provisional")
    if any(getattr(n, "value", n) == "rescue" for n in (getattr(analysis, "secondary_needs", None) or [])):
        flags.add("also_rescue")
    req_obj.flags = sorted(set(req_obj.flags) | flags)
    if model_reason and not req_obj.hoax_reason:
        req_obj.hoax_reason = model_reason[:300]
    source_words = citizen_text or report_text
    req_obj.summary = summary_from_report(source_words, machine_summary or req_obj.summary or source_words)
    if not (req_obj.raw_text or "").strip():
        req_obj.raw_text = (getattr(analysis, "original_text", None) or analysis.notes or getattr(analysis, "text_en", None) or "").strip() or req_obj.raw_text
    if trans_res.text_en:
        trans_res.text_en = guard_summary(citizen_text or report_text, trans_res.text_en)
        trans_res.translations["en"] = trans_res.text_en
    req_obj.ai_translation = trans_res.text_en
    req_obj.ai_source = ai_source
    req_obj.ai = ai_usage
    req_obj.translations = trans_res.translations
    req_obj.translation_confidence = trans_res.confidence
    urgency_res = scoring_engine.compute_urgency(req_obj)
    req_obj.urgency_score = urgency_res.score
    req_obj.urgency_reason = urgency_res.reason
    storage_service.save_request(req_obj, actor="intake_pipeline")
    _link_report(raw_report, req_obj, req_id, machine_summary, citizen_text or report_text)

    decision = None
    moved = before != (req_obj.type, req_obj.place_text, req_obj.ward_id)
    open_question = (
        req_obj.merged_into
        or joined
        or req_obj.possible_duplicate is not None
        or req_obj.dedupe_trace == "Kept separate."
    )
    if moved and not open_question:
        decision = _dedupe_and_rank(req_obj, analysis, payload.text or report_text, payload.source_id)
    else:
        matching_agent.find_matches(req_obj, top_n=3)
    finish(req_obj.merged_into or req_id)
    if req_obj.merged_into and req_obj.merged_into != req_id:
        finish(req_id)
    return decision


def _remember_words(req_obj: StoredRequest, report_id: str, text: str) -> None:
    """Keep the citizen's sentence and the count as they wrote it ('2-3', not only 3)."""
    words = (text or req_obj.raw_text or "").strip()
    bounds = people_bounds(words)
    span = bounds[2] if bounds else None
    if span:
        req_obj.people_span = span
        req_obj.count_spans = [span]
    if report_id and report_id not in req_obj.report_ids:
        req_obj.report_ids.append(report_id)
    if words:
        req_obj.report_quotes = [
            ReportQuote(report_id=report_id or req_obj.id, text=words[:500], people_span=span)
        ]


def _trace_for(decision, count_note: Optional[str], merged: bool) -> str:
    if merged:
        head = "Merged"
    elif getattr(decision, "review", False):
        head = "Possible duplicate, review"
    else:
        head = "Distinct"
    parts = [head]
    if decision.similarity is not None or decision.distance_km is not None or decision.minutes_apart is not None:
        parts.append(confidence_phrase(decision.similarity, decision.distance_km, decision.minutes_apart))
    if count_note and count_note not in " ".join(parts):
        parts.append(count_note)
    return ". ".join(parts)


def _demo_hindi_target_id(exclude_id: str) -> Optional[str]:
    hindi_ids = {
        report.request_id
        for report in storage_service.list_reports()
        if report.source_id == "demo_sample_hindi" and report.request_id
    }
    for row in storage_service.list_requests():
        if row.id == exclude_id or row.merged_into:
            continue
        if row.id in hindi_ids or "पुलिंकुन्नु" in (row.raw_text or ""):
            return row.id
    return None


def _apply_dedupe(req_obj: StoredRequest, decision, source_id: str = "") -> None:
    """Auto-merge above the threshold. Otherwise leave a review suggestion on this case."""
    from app.models.schemas import DedupeDecisionType
    from app.tools.case_merge import fold_case
    from app.tools.nlu_rules import counts_note

    if (source_id or "").startswith("demo_sample_duplicate"):
        target_id = decision.target_request_id or _demo_hindi_target_id(req_obj.id)
        if target_id:
            decision.target_request_id = target_id
            decision.review = True
            decision.decision = DedupeDecisionType.NEW
            if not decision.similarity:
                decision.similarity = 0.62

    merged = False
    if decision.decision.value == "duplicate" and decision.target_request_id:
        target = storage_service.get_request(decision.target_request_id)
        if target is not None and target.id != req_obj.id and not target.merged_into:
            fold_case(target.id, req_obj.id, decision.evidence, merged_by="auto_suggest")
            merged = True
            target = storage_service.get_request(target.id) or target
            fresh = storage_service.get_request(req_obj.id) or req_obj
            line = _trace_for(decision, target.count_note, True)
            target.dedupe_trace = line
            fresh.dedupe_trace = line
            fresh.merged_into = target.id
            req_obj.merged_into = target.id
            req_obj.merged_count = target.merged_count
            storage_service.save_request(target, actor="dedupe_agent")
            storage_service.save_request(fresh, actor="dedupe_agent")
            return
    if decision.review and decision.target_request_id:
        target = storage_service.get_request(decision.target_request_id)
        if target is not None:
            spans: List[str] = []
            for val in (target.people_span or (str(target.people_count) if target.people_count else ""),
                        req_obj.people_span or (str(req_obj.people_count) if req_obj.people_count else "")):
                if val and val not in spans:
                    spans.append(val)
            req_obj.count_spans = spans
            req_obj.count_note = counts_note(spans)
        line = _trace_for(decision, req_obj.count_note, False)
        req_obj.possible_duplicate = PossibleDuplicate(
            target_id=decision.target_request_id,
            confidence=float(decision.confidence or 0),
            similarity=float(decision.similarity or 0),
            distance_km=decision.distance_km,
            minutes=decision.minutes_apart,
            note=line,
        )
        req_obj.dedupe_trace = line
    else:
        req_obj.dedupe_trace = _trace_for(decision, req_obj.count_note, merged)
    storage_service.save_request(req_obj, actor="dedupe_agent")


def _mark_failed(req_id: str) -> None:
    req = storage_service.get_request(req_id)
    if req is None:
        return
    req.analysis_status = "failed"
    storage_service.save_request(req, actor="pipeline")


def _resolve_ward_id(place_text: Optional[str], report_text: str) -> Optional[str]:
    """Match 'Ward 7 Temple Road' to the gazetteer ward, including Hindi वार्ड."""
    return gazetteer.resolve_ward(place_text, report_text)


def _replay_idempotent(key: Optional[str]) -> Optional[ReportSubmitResponse]:
    """Return the original response for a repeated key. Parallel retries wait for the first save."""
    if not key:
        return None
    prior = storage_service.begin_or_replay(key)
    if prior and prior.get("request_id"):
        return ReportSubmitResponse(**prior)
    if prior and prior.get("_inflight"):
        for _ in range(40):
            time.sleep(0.05)
            done = storage_service.get_idempotent(key)
            if done and done.get("request_id"):
                return ReportSubmitResponse(**done)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This report is still being saved. It will retry.",
        )
    return None
