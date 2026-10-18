import logging
import re
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
from app.tools.nlu_rules import extract_place, people_bounds, people_count, place_is_usable, vulnerable_flags, count_is_stated, known_place, is_nobody_stranded
from app.agents.dedupe import confidence_phrase
from app.tools.trust import detect_hoax_or_flood, hoax_reason_for
from app.tools.gazetteer import gazetteer
from app.tools.input_gate import evaluate_input_gate
from app.api.public import public_code_for
from app.llm.client import llm_client
from app.config import settings

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


class LocationUpdateRequest(BaseModel):
    token: Optional[str] = None
    lat: float
    lng: float
    accuracy: Optional[float] = None
    source: Optional[str] = "gps"
    location_source: Optional[str] = None
    fix_time: Optional[float] = None


class ReportSubmitRequest(BaseModel):
    text: Optional[str] = ""
    channel: str = "text"  # "text" | "voice" | "photo"
    lang: str = "en"
    source_id: str = "anon_device"
    location_pin: Optional[Dict[str, float]] = None
    location_accuracy: Optional[float] = None
    location_source: Optional[str] = None
    scenario_id: str = "flood"
    voice_note_id: Optional[str] = None
    audio_base64: Optional[str] = None
    image_base64: Optional[str] = None
    photo_base64: Optional[str] = None
    mime_type: Optional[str] = None
    structured: Optional[StructuredReportFacts] = None
    idempotency_key: Optional[str] = None
    raw_text: Optional[str] = None
    # Chat answers after the first message, kept apart from the reporter's original sentence.
    chat_answers: Optional[List[str]] = None


class ReportSubmitResponse(BaseModel):
    report_id: str
    request_id: str
    public_code: Optional[str] = None
    status_token: str
    summary: str
    receipt: Optional[str] = None
    urgency_score: float
    dedupe_decision: str
    flags: List[str]
    safety_line: str
    transcript: Optional[str] = None
    asr_confidence: Optional[float] = None
    gate_outcome: Optional[str] = "report"
    gate_reply: Optional[str] = None
    is_case: bool = True


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
    photo_extracted = None
    photo_reading_fallback = False
    raw_photo = payload.photo_base64 or payload.image_base64
    if raw_photo:
        import base64

        try:
            b64_str = raw_photo.split(",", 1)[-1].strip()
            media_bytes = base64.b64decode(b64_str)
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
                b64_audio = payload.audio_base64.split(",", 1)[-1].strip()
                media_bytes = base64.b64decode(b64_audio)
                media_mime = "audio/wav"
            except Exception:
                media_bytes = None
        if payload.voice_note_id and media_bytes is None:
            from pathlib import Path

            wav = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "voice" / f"{payload.voice_note_id}.wav"
            if wav.exists():
                media_bytes = wav.read_bytes()
                media_mime = "audio/wav"

    # Citizen words stay the raw report. Voice uses the live transcript, not a stored caption.
    if payload.channel == "voice" and transcript:
        citizen_text = transcript.strip()
        report_text = citizen_text
    else:
        citizen_text = (payload.raw_text or payload.text or report_text or "").strip()
        if citizen_text:
            report_text = citizen_text

    has_photo = bool(media_bytes)
    if media_bytes and media_mime and payload.channel == "photo":
        try:
            photo_extracted = intake_agent.parse_media_report(
                report_text, media_bytes, media_mime, language_hint=payload.lang
            )
        except Exception as e:
            logger.warning("Intake media parsing at submit failed: %s", e)
            photo_reading_fallback = True
            photo_extracted = None
        if photo_extracted is None:
            photo_reading_fallback = True
        else:
            flags_set = set(getattr(photo_extracted, "flags", None) or [])
            has_fallback_flag = bool(flags_set & {"photo_fallback", "unparsed", "unparsed_model_output", "needs_human_review"})
            needs_review = bool(getattr(photo_extracted, "needs_human_review", False))
            if has_fallback_flag or needs_review:
                photo_reading_fallback = True

    is_unrelated_photo = False
    if photo_extracted is not None and not photo_reading_fallback:
        notes_low = (getattr(photo_extracted, "notes", "") or "").lower()
        has_em_notes = any(w in notes_low for w in ("rescue", "flood", "water", "trapped", "help", "emergency", "boat", "hazard"))
        t_val = getattr(getattr(photo_extracted, "type", None), "value", getattr(photo_extracted, "type", None))
        hz_val = getattr(getattr(photo_extracted, "hazard", None), "value", getattr(photo_extracted, "hazard", None))
        p_cnt = getattr(getattr(photo_extracted, "people", None), "count", None)
        has_err_flags = any(f in (getattr(photo_extracted, "flags", None) or []) for f in ("unparsed", "unparsed_model_output", "needs_human_review"))
        if (
            t_val == "other"
            and hz_val in ("none", "unknown")
            and not p_cnt
            and not has_em_notes
            and not has_err_flags
            and not bool((citizen_text or "").strip())
        ):
            is_unrelated_photo = True

    if is_unrelated_photo:
        status_token = f"tok_{uuid.uuid4().hex[:12]}"
        from app.tools.input_gate import _RESPONSES
        gate_reply = _RESPONSES["gibberish"].get(payload.lang or "en", _RESPONSES["gibberish"]["en"])
        flags = ["no_case", "gibberish", "unrelated_photo"]
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
            photo_base64=raw_photo,
            location_accuracy=payload.location_accuracy,
            location_source=payload.location_source,
        )
        req_id = f"req_{uuid.uuid4().hex[:10]}"
        req_obj = StoredRequest(
            id=req_id,
            public_code=public_code_for(raw_report.id),
            event_id="event_kerala_flood",
            pack_id=payload.scenario_id,
            type=IncidentType.OTHER,
            status=RequestStatus.CLOSED,
            flags=list(flags),
            summary=gate_reply,
            analysis_status="complete",
            raw_text=citizen_text or report_text or "",
            photo_base64=raw_photo,
            has_photo=True,
        )
        storage_service.save_request(req_obj, actor="photo_gate")
        _link_report(raw_report, req_obj, req_id, gate_reply, citizen_text or report_text)
        resp = _response_for(raw_report, req_obj, "new", flags, transcript, asr_confidence)
        if payload.idempotency_key:
            storage_service.save_idempotent(payload.idempotency_key, resp.model_dump())
        return resp

    # A3 Input gate evaluation (applies to text, voice transcript, and photo)
    outcome, gate_reply = evaluate_input_gate(
        report_text,
        lang=payload.lang,
        lang_hint=payload.lang,
        has_photo=has_photo,
        photo_is_emergency=True,
    )
    if outcome in ("greeting", "gibberish"):
        resp = ReportSubmitResponse(
            report_id="",
            request_id="",
            public_code=None,
            status_token="",
            summary=gate_reply,
            receipt=gate_reply,
            urgency_score=0.0,
            dedupe_decision="new",
            flags=["no_case", outcome],
            safety_line="In an immediate emergency call 112.",
            transcript=transcript,
            asr_confidence=asr_confidence,
            gate_outcome=outcome,
            gate_reply=gate_reply,
            is_case=False,
        )
        if payload.idempotency_key:
            storage_service.save_idempotent(payload.idempotency_key, resp.model_dump())
        return resp

    demo_sample = (payload.source_id or "").startswith("demo_sample_")
    # 1. Rate limiting check (flags only, never deletes). Demo sample buttons may be clicked again.
    if demo_sample:
        flags: List[str] = []
    else:
        is_limited, _ = rate_limiter.check_and_record(payload.source_id)
        flags = ["rate_limited"] if is_limited else []

    # 2. Store raw report immediately with generated status token and audio transcript
    status_token = f"tok_{uuid.uuid4().hex[:12]}"
    is_demo_loc = bool(payload.location_source in ("demo_pin", "demo"))
    raw_pin_lat = payload.location_pin.get("lat") if payload.location_pin else None
    raw_pin_lng = payload.location_pin.get("lng") if payload.location_pin else None
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
        photo_base64=raw_photo,
        lat=raw_pin_lat,
        lng=raw_pin_lng,
        location_accuracy=payload.location_accuracy,
        location_source=payload.location_source,
        demo_location=is_demo_loc,
    )
    if payload.chat_answers:
        raw_report.chat_answers = [str(x)[:500] for x in payload.chat_answers[:10]]
        if payload.raw_text and payload.channel != "voice":
            # The stored report is the reporter's first sentence; the answers sit beside it.
            raw_report.raw_text = payload.raw_text.strip()

    if payload.channel == "photo" and not citizen_text:
        citizen_text = "Flood photo"
        if not report_text:
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
    if photo_extracted and not photo_reading_fallback:
        extracted = photo_extracted
    elif has_photo and photo_reading_fallback:
        if "needs_human_review" not in flags:
            flags.append("needs_human_review")
    elif payload.channel == "photo" and extracted.type == IncidentType.OTHER:
        if "needs_human_review" not in flags:
            flags.append("needs_human_review")
    if has_photo and "has_photo" not in flags:
        flags.append("has_photo")
    machine_summary = _apply_card(extracted, payload, report_text)
    pin_lat, pin_lng, ward_id = _pin_for(payload, extracted, report_text)
    req_id = f"req_{uuid.uuid4().hex[:10]}"
    req_obj = StoredRequest(
        id=req_id,
        public_code=public_code_for(raw_report.id),
        event_id="event_kerala_flood",
        pack_id=payload.scenario_id,
        type=extracted.type,
        picked_type=(payload.structured.incident_type if payload.structured else None),
        place_text=extracted.place_text or (payload.location_pin.get("ward") if payload.location_pin else "") or "",
        ward_id=ward_id,
        lat=pin_lat,
        lng=pin_lng,
        location_accuracy=payload.location_accuracy,
        location_source=payload.location_source,
        demo_location=is_demo_loc,
        photo_base64=raw_photo,
        has_photo=has_photo,
        people_count=_stated_people(
            extracted.people.count,
            citizen_text or report_text,
            card_summary=(payload.structured.summary if payload.structured else None),
            channel=payload.channel,
        ),
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
    from app.tools.case_queue import begin_case
    # The life-threat check reads the chat answers too ("my father is not breathing" can come second).
    lane_text = "\n".join([citizen_text or report_text or ""] + list(payload.chat_answers or []))
    begin_case(req_obj, lane_text, others=storage_service.list_requests())
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
    is_explicit_edit = (
        payload.channel == "form"
        or (bool(facts.summary) and facts.summary != report_text)
    )
    # A6 RD-9914 fix: server ignores client people/place without a quoted span in report_text or explicit card edit
    if facts.people_count is not None:
        stated_in_text = count_is_stated(report_text, facts.people_count)
        stated_in_card = bool(facts.summary and count_is_stated(facts.summary, facts.people_count))
        heard_count = people_count(report_text)
        if not stated_in_text and not (is_explicit_edit and stated_in_card) and not heard_count:
            facts.people_count = None

    if facts.place_text is not None and facts.place_text.strip():
        card_p = facts.place_text.strip().lower()
        in_text = card_p in (report_text or "").lower()
        in_summary = bool(facts.summary and card_p in facts.summary.lower())
        kp = known_place(report_text)
        kp_match = bool(kp and kp.lower() == card_p)
        extracted_p = extract_place(report_text)
        if not in_text and not kp_match and not extracted_p and not (is_explicit_edit and in_summary):
            facts.place_text = None
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


def _stated_people(
    count: Optional[int],
    report_text: str,
    card_summary: Optional[str] = None,
    channel: Optional[str] = None,
) -> Optional[int]:
    """Unknown stays null. A card that says 0 is not a headcount the citizen gave."""
    bounds = people_bounds(report_text)
    stated = bounds[1] if bounds else None
    if count is None or count <= 0:
        return stated if stated else None
    if channel == "form" or (card_summary and count_is_stated(card_summary, count)):
        return count
    if not count_is_stated(report_text, count):
        return stated if stated else None
    return count


def _pin_for(payload: ReportSubmitRequest, extracted: ExtractedRequest, report_text: str) -> Tuple[float, float, Optional[str]]:
    # No pin and no confident place: store no location rather than a made-up default pin.
    pin_lat = payload.location_pin.get("lat") if payload.location_pin else None
    pin_lng = payload.location_pin.get("lng") if payload.location_pin else None
    ward_id = _resolve_ward_id(extracted.place_text, report_text)
    if not ward_id and pin_lat is not None and pin_lng is not None:
        from app.tools.gazetteer import ward_for_point
        ward_id = ward_for_point(pin_lat, pin_lng, max_km=15.0)
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


def build_receipt(req_obj: StoredRequest, raw_report: StoredReport, code: str) -> str:
    """Build receipt in reporter's language from the extracted record:
    'Received RD-xxxx. I understood: 2 people, water rising, near St. Mary's, Kainakary. Place: not stated.'
    Gemini failed/timeout/non-JSON -> 'Received RD-xxxx, a coordinator will read it.'
    """
    raw_text = raw_report.raw_text or req_obj.raw_text or ""
    # Detect script and language from raw_text, never blindly using raw_report.lang if script disagrees
    if re.search(r"[\u0D00-\u0D7F]", raw_text):
        lang = "ml"
    elif re.search(r"[\u0900-\u097F]", raw_text):
        lang = "hi"
    else:
        from app.tools.input_gate import is_manglish
        if is_manglish(raw_text) or (raw_report.lang or "").lower() == "manglish":
            lang = "manglish"
        elif (raw_report.lang or "").lower() in ("hinglish", "hi"):
            lang = "hinglish"
        else:
            lang = (raw_report.lang or "en").lower()
            if lang not in ("en", "hinglish", "manglish", "hi", "ml"):
                lang = "en"

    # Check if Gemini failed, timed out, unparsed; only fall back if no facts were extracted
    has_facts = bool(
        req_obj.people_count
        or (req_obj.hazard and getattr(req_obj.hazard, "value", req_obj.hazard) not in ("none", "unknown"))
        or (req_obj.vulnerable and any(req_obj.vulnerable.model_dump().values()))
        or (req_obj.place_text and req_obj.place_text.strip())
        or req_obj.photo_facts
    )
    is_failed = (
        req_obj.analysis_status == "failed"
        or "unparsed" in (req_obj.flags or [])
        or "unparsed_model_output" in (req_obj.flags or [])
        or (req_obj.ai and req_obj.ai.fallback_reason in ("timeout_45s", "error"))
    )

    if is_failed and not has_facts:
        if lang == "ml":
            return f"ലഭിച്ചു {code}, ഒരു കോർഡിനേറ്റർ ഇത് പരിശോധിക്കും."
        elif lang == "hi":
            return f"प्राप्त हुआ {code}, समन्वयक इसे पढ़ेंगे।"
        elif lang == "hinglish":
            return f"Mil gaya {code}, coordinator ise check karenge."
        elif lang == "manglish":
            return f"Labhichu {code}, oru coordinator ithu parishodhikkum."
        else:
            return f"Received {code}, a coordinator will read it."

    details: List[str] = []

    # 1. People count
    if req_obj.people_count:
        if lang == "ml":
            details.append(f"{req_obj.people_count} പേർ")
        elif lang == "hi":
            details.append(f"{req_obj.people_count} लोग")
        elif lang == "hinglish":
            details.append(f"{req_obj.people_count} log")
        elif lang == "manglish":
            details.append(f"{req_obj.people_count} per")
        else:
            details.append(f"{req_obj.people_count} people" if req_obj.people_count != 1 else "1 person")

    # 2. Hazard or condition or vulnerability
    words_low = raw_text.lower()
    pf_text = " ".join(req_obj.photo_facts or []).lower()

    water_rising_supported = (
        bool(re.search(
            r"\b(?:water\s+(?:is\s+)?rising|rising\s+water|water\s+level|flood|flooding|floodwater|submerged|water\s+entered|water\s+entering|water\s+came\s+in|water\s+inside)\b"
            r"|\b(?:paani|pani)\b[^.]{0,25}\b(?:badh|bhar|aa\s+gaya|ghus|chad)\b"
            r"|\b(?:vellam)\b[^.]{0,25}\b(?:kayar|kood|uyar|keri|vannu)\b"
            r"|വെള്ളം[^\s.,!?]*(?:\s+[^\s.,!?]+){0,3}\s*(?:ഉയര|കൂട|കയറ|വന്നു)"
            r"|പ്രളയം"
            r"|(?:पानी|जलस्तर)\s*(?:बढ़|बढ़|भर|आ\s*गया|घुस|आ\s*रहा)"
            r"|बाढ़",
            words_low,
            re.IGNORECASE,
        ))
        or bool(re.search(
            r"\b(?:water\s+(?:is\s+)?rising|rising\s+water|water\s+level|flood|flooding|flooded|submerged|water\s+entered|water\s+entering)\b",
            pf_text,
            re.IGNORECASE,
        ))
    )

    stranded_supported = (
        bool(re.search(
            r"\b(?:stranded|trapped|marooned|stuck|cut\s+off|isolated|fanse|fase|phase|atke|kudungi|ottappettu)\b"
            r"|കുടുങ്ങി|ഒറ്റപ്പെട്ടു|ഫംസേ|ഫംസ്|फंसे|फंस",
            words_low,
            re.IGNORECASE,
        )) and not is_nobody_stranded(raw_text)
        or bool(re.search(
            r"\b(?:stranded|trapped|marooned|stuck)\b",
            pf_text,
            re.IGNORECASE,
        ))
    )

    if req_obj.hazard and req_obj.hazard.value == "water_rising" and water_rising_supported:
        if lang == "ml":
            details.append("വെള്ളം ഉയരുന്നു")
        elif lang == "hi":
            details.append("पानी बढ़ रहा है")
        elif lang == "hinglish":
            details.append("paani badh raha hai")
        elif lang == "manglish":
            details.append("vellam kayarunnu")
        else:
            details.append("water rising")
    elif req_obj.hazard and req_obj.hazard.value == "stranded" and stranded_supported:
        if lang == "ml":
            details.append("കുടുങ്ങി")
        elif lang == "hi":
            details.append("फंसे हुए")
        elif lang == "hinglish":
            details.append("fanse hue")
        elif lang == "manglish":
            details.append("kudungi")
        else:
            details.append("stranded")

    cant_walk = bool(re.search(r"(?:can'?t|cannot|unable to|not able to)\s+walk|nadakkan\s*pattilla|chal\s*nahi\s*sakt", words_low))
    if req_obj.vulnerable:
        if req_obj.vulnerable.elderly:
            if lang == "ml":
                details.append("പ്രായമായവർക്ക് നടക്കാൻ കഴിയില്ല" if cant_walk else "പ്രായമായവർ")
            elif lang == "hi":
                details.append("बुजुर्ग चल नहीं सकते" if cant_walk else "बुजुर्ग")
            elif lang == "hinglish":
                details.append("elderly chal nahi sakte" if cant_walk else "elderly")
            elif lang == "manglish":
                details.append("elderly nadakkan pattilla" if cant_walk else "ammachi")
            else:
                details.append("elderly can't walk" if cant_walk else "elderly")
        if req_obj.vulnerable.child:
            if lang == "ml":
                details.append("കുട്ടികൾ")
            elif lang == "hi":
                details.append("बच्चे")
            elif lang == "hinglish":
                details.append("bachche")
            elif lang == "manglish":
                details.append("kuttikal")
            else:
                details.append("children")
        if req_obj.vulnerable.medical_need or getattr(req_obj.type, "value", req_obj.type) == "medical":
            if "breath" in words_low or "breathe" in words_low or "ശ്വാസം" in words_low or "साँस" in words_low or "swasam" in words_low:
                if lang == "ml":
                    details.append("ശ്വാസം കിട്ടുന്നില്ല")
                elif lang == "hi":
                    details.append("साँस लेने में तकलीफ")
                elif lang == "hinglish":
                    details.append("saans lene me dikkat")
                elif lang == "manglish":
                    details.append("swasam muttunnu")
                else:
                    details.append("someone not breathing")
            else:
                if lang == "ml":
                    details.append("വൈദ്യസഹായം")
                elif lang == "hi":
                    details.append("चिकित्सा सहायता")
                elif lang == "hinglish":
                    details.append("medical madad")
                elif lang == "manglish":
                    details.append("medical sahayam")
                else:
                    details.append("medical help")
        if req_obj.vulnerable.pregnant:
            if lang == "ml":
                details.append("ഗർഭിണി")
            elif lang == "hi":
                details.append("गर्भवती")
            elif lang == "hinglish":
                details.append("pregnant woman")
            elif lang == "manglish":
                details.append("garbhini")
            else:
                details.append("pregnant woman")

    for pf in (req_obj.photo_facts or []):
        if pf not in details:
            details.append(pf)

    # 3. Place
    if req_obj.place_text and req_obj.place_text.strip():
        p = req_obj.place_text.strip()
        if lang == "ml":
            details.append(f"{p} അടുത്ത്")
        elif lang == "hi":
            details.append(f"{p} के पास")
        elif lang == "hinglish":
            details.append(f"{p} ke paas")
        elif lang == "manglish":
            details.append(f"{p} aduthu")
        else:
            details.append(f"near {p}")
    else:
        if lang == "ml":
            details.append("സ്ഥലം: പറഞ്ഞിട്ടില്ല")
        elif lang == "hi":
            details.append("स्थान: बताया नहीं")
        elif lang == "hinglish":
            details.append("Jagah: not stated")
        elif lang == "manglish":
            details.append("Sthalam: paranjittilla")
        else:
            details.append("Place: not stated")

    joined_details = ", ".join(details)
    if lang == "ml":
        return f"ലഭിച്ചു {code}. മനസ്സിലായത്: {joined_details}."
    elif lang == "hi":
        return f"प्राप्त हुआ {code}। समझ आया: {joined_details}।"
    elif lang == "hinglish":
        return f"Mil gaya {code}. Samajh aaya: {joined_details}."
    elif lang == "manglish":
        return f"Labhichu {code}. Manassilayathu: {joined_details}."
    else:
        return f"Received {code}. I understood: {joined_details}."


def _reporter_summary(raw_report: StoredReport, req_obj: StoredRequest) -> str:
    """What the reporter sees after sending: a clean one-line summary in their language."""
    if req_obj.hoax_reason or "hoax" in (req_obj.flags or []):
        text = req_obj.ai_translation or req_obj.summary or ""
        non_empty = [line.strip() for line in text.splitlines() if line.strip()]
        return non_empty[0] if non_empty else (req_obj.summary or "")
    try:
        from app.agents.chat_intake import _slot_summary

        short = _slot_summary(req_obj.type, req_obj.people_count, req_obj.place_text, raw_report.lang or "en")
        if short:
            return short
    except Exception:
        pass
    fallback = req_obj.ai_translation or req_obj.summary or raw_report.raw_text or ""
    if fallback:
        from app.agents.summary import short_faithful_summary
        return short_faithful_summary(fallback)
    return ""


def _response_for(
    raw_report: StoredReport,
    req_obj: StoredRequest,
    decision: str,
    flags: List[str],
    transcript: Optional[str],
    asr_confidence: Optional[float],
) -> ReportSubmitResponse:
    pub_code = req_obj.public_code or public_code_for(raw_report.id)
    req_obj.public_code = pub_code
    reading = req_obj.analysis_status == "analysing" and not (req_obj.ai_translation or "").strip()
    receipt = "" if reading else build_receipt(req_obj, raw_report, pub_code)
    summary_text = _reporter_summary(raw_report, req_obj) or req_obj.summary or ""
    if "no_case" in flags:
        from app.tools.input_gate import _RESPONSES
        gate_reply = _RESPONSES["gibberish"].get(raw_report.lang or "en", _RESPONSES["gibberish"]["en"])
        return ReportSubmitResponse(
            report_id=raw_report.id,
            request_id=req_obj.id,
            public_code=pub_code,
            status_token=raw_report.status_token or "",
            summary=req_obj.summary or gate_reply,
            receipt=req_obj.summary or gate_reply,
            urgency_score=0.0,
            dedupe_decision="new",
            flags=list(flags),
            safety_line="In an immediate emergency call 112.",
            transcript=transcript,
            asr_confidence=asr_confidence,
            gate_outcome="gibberish",
            gate_reply=gate_reply,
            is_case=False,
        )
    return ReportSubmitResponse(
        report_id=raw_report.id,
        request_id=req_obj.id,
        public_code=pub_code,
        status_token=raw_report.status_token or "",
        summary=summary_text,
        receipt=receipt,
        urgency_score=req_obj.urgency_score,
        dedupe_decision=decision,
        flags=list(flags),
        safety_line="In an immediate emergency call 112.",
        transcript=transcript,
        asr_confidence=asr_confidence,
        gate_outcome="report",
        gate_reply=None,
        is_case=True,
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


def _keep_rules_after_timeout(late: StoredRequest, analysis, ai_usage, report_text: str, payload):
    """Timeout is final. A late model reply never overwrites a case rules already finished.

    What Gemini would have changed is kept only as a re-check diff (Gemini re-checked · X → Y).
    """
    from app.tools.case_queue import _diff

    proposed = {
        "people_count": getattr(getattr(analysis, "people", None), "count", None),
        "place_text": getattr(analysis, "place_text", None),
        "type": getattr(analysis, "type", None),
    }
    diff = _diff(late, {k: v for k, v in proposed.items() if v not in (None, "")})
    late.ai_queue.recheck_diff = diff or None
    if diff:
        late.ai_queue.engine = "gemini_rechecked"
    storage_service.save_request(late, actor="timeout_guard")
    ruled = extract_with_rules(report_text)
    _apply_card(ruled, payload, report_text)
    for attr in ("text_en", "text_hi", "translation_confidence", "likely_hoax", "hoax_reason"):
        if hasattr(analysis, attr) and hasattr(ruled, attr):
            try:
                setattr(ruled, attr, getattr(analysis, attr))
            except Exception:
                pass
    usage = ai_usage.model_copy()
    usage.provider = "fallback"
    usage.cached = False
    usage.fallback_reason = "timeout_45s"
    return ruled, usage


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
        try:
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
        except Exception as e:
            logger.warning("Intake parsing failed in _refine_with_model: %s", e)
            from app.agents.intake import ReportAnalysis
            analysis = ReportAnalysis(
                type=IncidentType.OTHER,
                hazard=HazardType.UNKNOWN,
                notes=f"Parsing error: {str(e)}",
                needs_human_review=True,
                flags=["unparsed", "needs_human_review"],
            )
        last_call = getattr(llm_client, "last_ai", None)
        if last_call is not None:
            ai_usage = last_call.model_copy()
        else:
            from app.models.schemas import AiCall
            ai_usage = AiCall(provider="fallback")

    if bool(media_bytes):
        flags_set = set(getattr(analysis, "flags", None) or [])
        has_fallback_flag = bool(flags_set & {"photo_fallback", "unparsed", "unparsed_model_output", "needs_human_review"})
        needs_rev = bool(getattr(analysis, "needs_human_review", False))

        is_fallback_reading = (analysis is None) or has_fallback_flag or needs_rev
        if not is_fallback_reading:
            notes_low = (getattr(analysis, "notes", "") or "").lower()
            has_em_notes = any(w in notes_low for w in ("rescue", "flood", "water", "trapped", "help", "emergency", "boat", "hazard"))
            t_val = getattr(getattr(analysis, "type", None), "value", getattr(analysis, "type", None))
            hz_val = getattr(getattr(analysis, "hazard", None), "value", getattr(analysis, "hazard", None))
            has_err_flags = any(f in (getattr(analysis, "flags", None) or []) for f in ("unparsed", "unparsed_model_output", "needs_human_review"))
            is_unrelated = (
                t_val == "other"
                and hz_val in ("none", "unknown")
                and not (getattr(analysis, "people", None) and getattr(analysis.people, "count", None))
                and not has_em_notes
                and not has_err_flags
                and not bool((citizen_text or "").strip() and (citizen_text or "").strip() != "Flood photo")
            )
            if is_unrelated:
                for f in ("no_case", "gibberish", "unrelated_photo"):
                    if f not in flags:
                        flags.append(f)
                from app.tools.input_gate import _RESPONSES
                gate_reply = _RESPONSES["gibberish"].get(payload.lang or "en", _RESPONSES["gibberish"]["en"])
                req_target = storage_service.get_request(req_id)
                if req_target:
                    req_target.status = RequestStatus.CLOSED
                    req_target.analysis_status = "complete"
                    for f in ("no_case", "gibberish", "unrelated_photo"):
                        if f not in req_target.flags:
                            req_target.flags.append(f)
                    req_target.summary = gate_reply
                    storage_service.save_request(req_target, actor="photo_gate")
                raw_target = storage_service.get_report(report_id)
                if raw_target:
                    for f in ("no_case", "gibberish", "unrelated_photo"):
                        if f not in raw_target.flags:
                            raw_target.flags.append(f)
                    storage_service.save_report(raw_target)
                from app.models.schemas import DedupeDecision, DedupeDecisionType
                return DedupeDecision(decision=DedupeDecisionType.NEW, evidence=["unrelated_photo"])
        else:
            if "needs_human_review" not in flags:
                flags.append("needs_human_review")
            req_target = storage_service.get_request(req_id)
            if req_target and "needs_human_review" not in req_target.flags:
                req_target.flags.append("needs_human_review")
                storage_service.save_request(req_target, actor="photo_fallback_guard")

    trans_res = _translation_for(report_text, analysis, ai_usage)
    source_words = citizen_text or report_text
    from app.tools.translation import faithful_english, translation_drops_facts
    if trans_res.text_en and translation_drops_facts(source_words, trans_res.text_en):
        fixed = faithful_english(source_words)
        trans_res.text_en = fixed
        trans_res.translations["en"] = fixed
    from app.agents.intake import union_with_rules
    union_with_rules(analysis, source_words, trans_res.text_en or "")
    if (payload.source_id or "") == "judge_input" and ai_usage.provider == "cache":
        ai_usage.provider = "fallback"
        ai_usage.cached = False
        ai_usage.fallback_reason = "judge_no_replay"
    ai_source = {"gemini": "gemini", "cache": "recorded", "antigravity-local": "antigravity-local",
                 "openai_compat": "openai_compat"}.get(
        ai_usage.provider, "offline_fallback"
    )
    late = storage_service.get_request(req_id)
    if late is not None and late.ai_queue is not None and "timedOut" in (late.ai_queue.flags or []) and ai_usage.provider != "fallback":
        analysis, ai_usage = _keep_rules_after_timeout(late, analysis, ai_usage, report_text, payload)
        ai_source = "offline_fallback"
    model_reason = (getattr(analysis, "hoax_reason", None) or "").strip()
    if getattr(analysis, "likely_hoax", False) or model_reason:
        for flag in ("hoax", "likely_hoax"):
            if flag not in flags:
                flags.append(flag)
    machine_summary = _apply_card(analysis, payload, report_text)
    if getattr(analysis, "flags", None):
        for f in analysis.flags:
            if f not in flags:
                flags.append(f)
    if trans_res.is_low_confidence and "low_translation_confidence" not in flags:
        flags.append("low_translation_confidence")
        flags.append("needs_human_review")

    req_obj = storage_service.get_request(req_id)
    raw_report = storage_service.get_report(report_id)
    if req_obj is None or raw_report is None:
        raise RuntimeError("report disappeared before enrichment")

    before = (req_obj.type, req_obj.place_text, req_obj.ward_id)
    from app.tools.case_queue import promote_life_threat
    promote_life_threat(req_obj, trans_res.text_en)
    joined = (req_obj.merged_count or 1) > 1
    pin_lat, pin_lng, ward_id = _pin_for(payload, analysis, report_text)
    req_obj.type = analysis.type
    chosen_place = analysis.place_text or req_obj.place_text
    if not place_is_usable(chosen_place):
        chosen_place = extract_place(citizen_text or report_text)
    req_obj.place_text = chosen_place if place_is_usable(chosen_place) else ""
    req_obj.ward_id = ward_id or req_obj.ward_id
    req_obj.lat = pin_lat if pin_lat is not None else req_obj.lat
    req_obj.lng = pin_lng if pin_lng is not None else req_obj.lng
    if getattr(raw_report, "demo_location", False) or getattr(req_obj, "demo_location", False):
        req_obj.demo_location = True
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
    if payload.channel == "photo":
        note = (getattr(analysis, "notes", None) or "").strip()
        if note and note not in ("Flood photo", "Empty report received"):
            req_obj.photo_facts = [note] if "photo" in note.lower() else [f"from photo: {note}"]
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
        head = "New case: no open report matched it"
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
    """Never merges. A likely duplicate or update leaves a review flag on this case."""
    from app.models.schemas import DedupeDecisionType
    from app.tools.nlu_rules import counts_note

    if (source_id or "").startswith("demo_sample_duplicate"):
        target_id = decision.target_request_id or _demo_hindi_target_id(req_obj.id)
        if target_id:
            decision.target_request_id = target_id
            decision.review = True
            decision.decision = DedupeDecisionType.NEW
            if not decision.similarity:
                decision.similarity = 0.62

    # Never auto-merge. A likely duplicate or "now N people" update is flagged
    # for a person to Merge / Keep separate; scoring plans for the merged facts.
    if decision.decision.value in ("duplicate", "update") and decision.target_request_id:
        decision.review = True
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
            nums = [int(v) for v in spans if str(v).isdigit()]
            if len(nums) == 2 and nums[0] != nums[1]:
                from app.api.public import case_code
                code = case_code(target)
                req_obj.count_note = f"Counts differ: {nums[0]} vs {nums[1]} people → plan for {max(nums)} · possible duplicate of {code}"
        line = _trace_for(decision, req_obj.count_note, False)
        req_obj.possible_duplicate = PossibleDuplicate(
            target_id=decision.target_request_id,
            target_code=getattr(target, "public_code", None) if target is not None else None,
            confidence=float(decision.confidence or 0),
            similarity=float(decision.similarity or 0),
            distance_km=decision.distance_km,
            minutes=decision.minutes_apart,
            note=line,
        )
        req_obj.dedupe_trace = line
    else:
        req_obj.dedupe_trace = _trace_for(decision, req_obj.count_note, False)
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


@router.post("/reports/{report_id}/location")
def update_report_location(report_id: str, payload: LocationUpdateRequest):
    report = storage_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if payload.token and report.status_token and report.status_token != payload.token:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not (-90.0 <= payload.lat <= 90.0) or not (-180.0 <= payload.lng <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Coordinates out of range: lat must be in [-90, 90] and lng in [-180, 180]",
        )

    source_val = payload.location_source or payload.source or "gps"
    is_demo = (source_val in ("demo_pin", "demo")) or (payload.location_source in ("demo_pin", "demo")) or (payload.source in ("demo_pin", "demo"))
    if is_demo:
        source = "demo_pin"
    else:
        source = source_val
        now = time.time()
        is_stale_fix = False
        if payload.fix_time is not None:
            fix_sec = payload.fix_time / 1000.0 if payload.fix_time > 1e11 else payload.fix_time
            if (now - fix_sec) > 600:
                is_stale_fix = True
        if (payload.accuracy is not None and payload.accuracy > 200) or is_stale_fix:
            source = "approximate"

    report.lat = payload.lat
    report.lng = payload.lng
    report.location_accuracy = payload.accuracy
    report.location_source = source
    if is_demo:
        report.demo_location = True

    req_id = report.case_id or report.request_id
    if req_id:
        req = storage_service.get_request(req_id)
        if req:
            req.lat = payload.lat
            req.lng = payload.lng
            req.location_accuracy = payload.accuracy
            req.location_source = source
            if is_demo:
                req.demo_location = True
            from app.tools.gazetteer import ward_for_point
            resolved = ward_for_point(payload.lat, payload.lng, max_km=15.0)
            if resolved:
                req.ward_id = resolved
            elif not req.ward_id:
                req.ward_id = gazetteer.resolve_ward(req.place_text, req.raw_text)
            from app.agents.matching import matching_agent
            matching_agent.find_matches(req, top_n=3, save_to_storage=True)
            storage_service.save_request(req, actor="location_update")
    storage_service.save_report(report)
    return {
        "status": "ok",
        "ok": True,
        "report_id": report_id,
        "lat": payload.lat,
        "lng": payload.lng,
        "accuracy": payload.accuracy,
        "source": source,
        "demo_location": report.demo_location,
    }
