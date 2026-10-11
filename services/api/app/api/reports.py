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


@router.post("/reports", response_model=ReportSubmitResponse)
def submit_report(payload: ReportSubmitRequest):
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

    # 3. Extract structured request from text / transcript, then apply confirmed card edits.
    extracted = intake_agent.parse_report(report_text, language_hint=payload.lang)
    if payload.structured:
        facts = payload.structured
        if facts.incident_type:
            extracted.type = IncidentType(facts.incident_type)
        if facts.place_text:
            extracted.place_text = facts.place_text
        if facts.people_count is not None:
            extracted.people.count = facts.people_count
            extracted.people.confidence = 1.0
        if facts.vulnerable:
            for flag, value in facts.vulnerable.items():
                if hasattr(extracted.vulnerable, flag):
                    setattr(extracted.vulnerable, flag, bool(value))
        if facts.hazard:
            extracted.hazard = HazardType(facts.hazard)
        if facts.summary:
            report_text = facts.summary

    # 4. Deduplication against active requests
    existing = storage_service.list_requests()
    pin_lat = payload.location_pin.get("lat") if payload.location_pin else 26.85
    pin_lng = payload.location_pin.get("lng") if payload.location_pin else 80.93

    candidates = dedupe_agent.prefilter_candidates(
        new_req=extracted,
        new_lat=pin_lat,
        new_lng=pin_lng,
        new_ward=None,
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
        event_id="event_riverbend_flood",
        pack_id=payload.scenario_id,
        type=extracted.type,
        place_text=extracted.place_text or "Riverbend Area",
        lat=pin_lat,
        lng=pin_lng,
        people_count=extracted.people.count or 1,
        vulnerable=extracted.vulnerable,
        hazard=extracted.hazard,
        status=RequestStatus.NEW,
        flags=flags,
        raw_text=report_text,
        ai_translation=trans_res.text_en,
        translations=trans_res.translations,
        translation_confidence=trans_res.confidence,
    )

    # 5. Score urgency
    urgency_res = scoring_engine.compute_urgency(req_obj)
    req_obj.urgency_score = urgency_res.score
    req_obj.urgency_reason = urgency_res.reason

    # Save request
    storage_service.save_request(req_obj, actor="intake_pipeline")
    raw_report.request_id = req_id

    # Handle cluster if duplicate
    if decision.decision.value == "duplicate" and decision.target_request_id:
        storage_service.create_cluster(
            request_ids=[decision.target_request_id, req_id],
            evidence=decision.evidence,
            merged_by="auto_suggest"
        )

    return ReportSubmitResponse(
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
