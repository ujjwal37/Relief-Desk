import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.agents.chat_intake import chat_intake_agent, ChatTurnResponse, ConfirmationCardData
from app.agents.intake import intake_agent
from app.agents.dedupe import dedupe_agent
from app.tools.storage import storage_service
from app.tools.scoring import scoring_engine
from app.tools.ratelimit import rate_limiter
from app.tools.asr import asr_service, VoiceNoteMetadata, ASRResult
from app.tools.translation import translation_service, TranslationResult
from app.models.firestore_models import StoredRequest, RequestStatus
from app.models.schemas import HazardType, IncidentType
from app.tools.request_contract import canonical_request_dict
from app.tools.nlu_rules import extract_place, vulnerable_flags
from app.tools.trust import detect_hoax_or_flood
from app.tools.gazetteer import gazetteer
from app.llm.client import llm_client

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

    # 0. ASR Audio transcription
    transcript: Optional[str] = None
    asr_confidence: Optional[float] = None
    report_text: str = payload.text or ""

    if payload.channel == "voice" or payload.voice_note_id or payload.audio_base64:
        asr_res = asr_service.transcribe(
            voice_note_id=payload.voice_note_id,
            audio_base64=payload.audio_base64,
            lang_hint=payload.lang
        )
        transcript = asr_res.transcript
        asr_confidence = asr_res.asr_confidence
        if not report_text.strip():
            report_text = transcript

    # 1. Rate limiting check (flags only, never deletes)
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

    # Citizen words stay the raw report. The card summary is a separate field.
    citizen_text = (payload.raw_text or payload.text or report_text or "").strip()
    if citizen_text:
        report_text = citizen_text

    for flag in detect_hoax_or_flood(
        storage_service.list_reports(),
        citizen_text or report_text,
        payload.source_id,
    ):
        if flag not in flags:
            flags.append(flag)

    # 3. Extract, then overlay the confirmed card. Chat and form share one canonical shape.
    extracted = intake_agent.parse_report(report_text, language_hint=payload.lang)
    # Capture this before translation or the explainer overwrites the client flag.
    ai_usage = llm_client.last_ai.model_copy()
    ai_source = {"gemini": "gemini", "cache": "recorded"}.get(ai_usage.provider, "offline_fallback")
    machine_summary = None
    if payload.structured:
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
        if facts.summary:
            machine_summary = canon["summary"]
        # Keep a short confirmed place. A sentence-length card place is the old bad parse.
        card_place = (facts.place_text or "").strip()
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

    # 4. Deduplication against active requests
    existing = storage_service.list_requests()
    pin_lat = payload.location_pin.get("lat") if payload.location_pin else 9.498
    pin_lng = payload.location_pin.get("lng") if payload.location_pin else 76.339
    ward_id = _resolve_ward_id(extracted.place_text, report_text)
    geo = gazetteer.lookup(extracted.place_text or report_text or "")
    if not payload.location_pin and geo.lat is not None and geo.lng is not None and not geo.is_low_confidence:
        pin_lat, pin_lng = geo.lat, geo.lng

    candidates = dedupe_agent.prefilter_candidates(
        new_req=extracted,
        new_lat=pin_lat,
        new_lng=pin_lng,
        new_ward=ward_id,
        existing_requests=existing
    )
    decision = dedupe_agent.evaluate(payload.text, extracted, candidates)

    # Translate report and evaluate translation confidence
    trans_res = translation_service.translate_report(report_text)
    if trans_res.is_low_confidence and "low_translation_confidence" not in flags:
        flags.append("low_translation_confidence")
        flags.append("needs_human_review")

    req_id = f"req_{uuid.uuid4().hex[:10]}"
    req_obj = StoredRequest(
        id=req_id,
        event_id="event_kerala_flood",
        pack_id=payload.scenario_id,
        type=extracted.type,
        place_text=extracted.place_text or "Alappuzha",
        ward_id=ward_id,
        lat=pin_lat,
        lng=pin_lng,
        people_count=extracted.people.count or 1,
        vulnerable=extracted.vulnerable,
        hazard=extracted.hazard,
        status=RequestStatus.NEW,
        flags=flags,
        raw_text=citizen_text or report_text,
        summary=machine_summary,
        ai_translation=trans_res.text_en,
        ai_source=ai_source,
        ai=ai_usage,
        translations=trans_res.translations,
        translation_confidence=trans_res.confidence,
    )

    # 5. Score urgency
    urgency_res = scoring_engine.compute_urgency(req_obj)
    req_obj.urgency_score = urgency_res.score
    req_obj.urgency_reason = urgency_res.reason

    # A second caller about the same place and people folds into the open case.
    if decision.decision.value == "duplicate" and decision.target_request_id:
        target = storage_service.get_request(decision.target_request_id)
        if target is not None:
            target.merged_count = (target.merged_count or 1) + 1
            if raw_report.id not in target.report_ids:
                target.report_ids.append(raw_report.id)
            storage_service.save_request(target, actor="dedupe_agent")
            req_obj.merged_into = target.id
            req_obj.merged_count = target.merged_count
            raw_report.request_id = target.id

    # Save request
    storage_service.save_request(req_obj, actor="intake_pipeline")
    if raw_report.request_id is None:
        raw_report.request_id = req_id

    # Handle cluster if duplicate
    if decision.decision.value == "duplicate" and decision.target_request_id:
        storage_service.create_cluster(
            request_ids=[decision.target_request_id, req_id],
            evidence=decision.evidence,
            merged_by="auto_suggest"
        )

    from app.agents.pipeline import spawn_analysis
    spawn_analysis(req_obj.merged_into or req_obj.id)

    response = ReportSubmitResponse(
        report_id=raw_report.id,
        request_id=req_id,
        status_token=status_token,
        summary=f"{req_obj.people_count} person(s) needing {req_obj.type.value} at {req_obj.place_text}",
        urgency_score=urgency_res.score,
        dedupe_decision=decision.decision.value,
        flags=flags,
        safety_line="In an immediate emergency call 112.",
        transcript=transcript,
        asr_confidence=asr_confidence,
    )
    storage_service.save_idempotent(payload.idempotency_key, response.model_dump())
    return response


@router.post("/reports", response_model=ReportSubmitResponse)
def submit_report(payload: ReportSubmitRequest):
    try:
        return _submit_report_impl(payload)
    except Exception:
        storage_service.release_idempotent(payload.idempotency_key)
        raise


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
