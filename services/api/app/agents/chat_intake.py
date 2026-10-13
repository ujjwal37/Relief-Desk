import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.schemas import (
    IncidentType,
    HazardType,
    ExtractedRequest,
    VulnerableFlags,
    PeopleInfo,
)
from app.agents.intake import intake_agent
from app.tools.scenario_loader import scenario_registry
from app.tools.gazetteer import gazetteer

logger = logging.getLogger("relief_desk.chat_intake")

_INJECTION = re.compile(
    r"\b(?:ignore (?:all )?previous instructions|system prompt|jailbreak|bypass)\b",
    re.IGNORECASE,
)
_MEDICINE = re.compile(
    r"\b(?:what medicine|which medicine|prescribe|tablet|antibiotic|dose|dosage|dawai|"
    r"kya dawai|painkiller|aspirin|paracetamol|ibuprofen)\b",
    re.IGNORECASE,
)
_SWIM = re.compile(
    r"\b(?:is it safe to swim|safe to swim|can i swim|should i swim|swim in|"
    r"is the water safe|can i drink the water|should i drink)\b",
    re.IGNORECASE,
)

# Short close, with no pipe summary and no raw hazard or type keys.
_READY = {
    "en": "Details are ready. Review the card below and tap Send.",
    "hi": "विवरण तैयार है। नीचे दिए कार्ड की जाँच करें और भेजें।",
    "hinglish": "Details ready hain. Neeche wala card check karke bhej dijiye.",
    "ml": "വിവരങ്ങൾ തയ്യാർ. താഴെയുള്ള കാർഡ് പരിശോധിച്ച് അയയ്ക്കുക.",
}


def injection_pattern(message: str) -> bool:
    return _INJECTION.search(message) is not None


def safety_refusal_lines(message: str) -> Optional[List[str]]:
    """Return fixed safety-line ids, or None when the message is a normal report."""
    if _MEDICINE.search(message):
        return ["no_medical_advice", "call_112"]
    if _SWIM.search(message):
        return ["move_to_higher_ground", "call_112"]
    return None


def pack_notice(scenario, lang: str) -> str:
    """First non-112 safety line on the active pack, otherwise call 112."""
    ids = list(getattr(scenario, "safety_line_ids", None) or ["call_112"])
    chosen = next((line_id for line_id in ids if line_id != "call_112"), ids[0])
    return scenario_registry.get_safety_line(chosen, lang=lang)


def reply_is_only_safety_lines(reply: str) -> bool:
    catalog = []
    for line in scenario_registry._safety_lines.values():
        for lang in ("en", "hi", "hinglish", "ml"):
            text = line.get(lang)
            if text:
                catalog.append(text)
    catalog.append("Call 112 in an emergency.")
    remaining = reply
    for text in sorted(catalog, key=len, reverse=True):
        remaining = remaining.replace(text, " ")
    remaining = re.sub(r"[\s\.]+", "", remaining)
    return remaining == ""


class ConfirmationCardData(BaseModel):
    incident_type: str
    place_text: Optional[str]
    people_count: Optional[int]
    vulnerable: Dict[str, bool]
    hazard: str
    summary: str
    safety_line: Optional[str] = None
    ready_to_submit: bool = True


class ChatTurnState(BaseModel):
    session_id: str
    scenario_id: str = "flood"
    language: str = "en"
    turn_count: int = 0
    extracted_so_far: ExtractedRequest = Field(default_factory=ExtractedRequest)
    messages_history: List[Dict[str, str]] = Field(default_factory=list)
    is_complete: bool = False
    confirmation_card: Optional[ConfirmationCardData] = None


class ChatTurnResponse(BaseModel):
    session_id: str
    bot_message: str
    turn_count: int
    missing_fields: List[str]
    confirmation_card: Optional[ConfirmationCardData] = None
    safety_line: Optional[str] = None


class ChatIntakeAgent:
    def __init__(self):
        self._sessions: Dict[str, ChatTurnState] = {}

    def get_or_create_session(self, session_id: Optional[str], scenario_id: str = "flood") -> ChatTurnState:
        s_id = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        if s_id not in self._sessions:
            self._sessions[s_id] = ChatTurnState(session_id=s_id, scenario_id=scenario_id)
        return self._sessions[s_id]

    def process_turn(
        self,
        session_id: Optional[str],
        user_message: str,
        scenario_id: str = "flood",
        lang_override: Optional[str] = None,
        location_pin: Optional[Dict[str, float]] = None,
    ) -> ChatTurnResponse:
        state = self.get_or_create_session(session_id, scenario_id)
        state.turn_count += 1
        state.messages_history.append({"role": "user", "text": user_message})

        scenario = scenario_registry.get_scenario(state.scenario_id) or scenario_registry.get_scenario("flood")
        # The app language wins over a guess from the words, so a Hindi UI
        # does not flip to English after an English chip.
        if lang_override:
            lang = lang_override
            state.language = lang_override
        else:
            lang = state.language or "en"

        # 1. Safety guardrail: advice and injection requests return fixed lines only.
        advice = safety_refusal_lines(user_message)
        if advice or injection_pattern(user_message):
            line_ids = advice or ["no_medical_advice", "call_112"]
            parts = [scenario_registry.get_safety_line(line_id, lang=lang) for line_id in line_ids]
            reply = " ".join(parts)
            state.messages_history.append({"role": "assistant", "text": reply})
            return ChatTurnResponse(
                session_id=state.session_id,
                bot_message=reply,
                turn_count=state.turn_count,
                missing_fields=["safety_refusal"],
                safety_line=parts[-1],
                confirmation_card=None,
            )

        # 2. Extract facts from current turn
        extracted_turn = intake_agent.parse_report(user_message, language_hint=lang)
        current = state.extracted_so_far

        # Detect language only when the client did not choose one.
        if extracted_turn.language and not lang_override:
            lang = extracted_turn.language.value
            state.language = lang

        # Merge extracted facts
        if extracted_turn.type != IncidentType.OTHER:
            current.type = extracted_turn.type
        elif current.type == IncidentType.OTHER and scenario and scenario.incident_types:
            current.type = IncidentType(scenario.incident_types[0])

        if extracted_turn.place_text:
            current.place_text = extracted_turn.place_text
        elif location_pin and not current.place_text:
            current.place_text = f"Pin ({location_pin.get('lat', 9.498):.4f}, {location_pin.get('lng', 76.339):.4f})"

        if extracted_turn.people.count is not None:
            current.people = extracted_turn.people

        # Merge vulnerable flags
        for flag in ["child", "elderly", "disabled", "pregnant", "medical_need"]:
            if getattr(extracted_turn.vulnerable, flag):
                setattr(current.vulnerable, flag, True)

        if extracted_turn.hazard != HazardType.UNKNOWN:
            current.hazard = extracted_turn.hazard

        # 3. Compute Missing Fields
        missing = []
        if not current.place_text:
            missing.append("location")
        if current.people.count is None:
            missing.append("people_count")
        if not any(getattr(current.vulnerable, f) for f in ["child", "elderly", "disabled", "pregnant", "medical_need"]):
            # If vulnerable questions not addressed and turn count is early
            if state.turn_count <= 2:
                missing.append("vulnerable")
        if current.hazard in (HazardType.UNKNOWN, HazardType.NONE):
            if state.turn_count <= 2:
                missing.append("hazard")

        # 4. If all critical fields present, or turn count reached threshold (<= 4 turns hero case)
        if not missing or state.turn_count >= 4:
            state.is_complete = True
            summary_parts = [
                f"{current.people.count or 1} person{'s' if (current.people.count or 1) > 1 else ''} needing {current.type.value}"
            ]
            if current.place_text:
                summary_parts.append(f"at {current.place_text}")
            vuln_list = [k for k, v in current.vulnerable.model_dump().items() if v]
            if vuln_list:
                summary_parts.append(f"Vulnerable: {', '.join(vuln_list)}")
            if current.hazard != HazardType.NONE:
                summary_parts.append(f"Hazard: {current.hazard.value}")

            summary_text = " | ".join(summary_parts)
            card = ConfirmationCardData(
                incident_type=current.type.value,
                place_text=current.place_text or "Champakulam",
                people_count=current.people.count or 1,
                vulnerable=current.vulnerable.model_dump(),
                hazard=current.hazard.value,
                summary=summary_text,
                safety_line=pack_notice(scenario, lang),
                ready_to_submit=True,
            )
            state.confirmation_card = card

            bot_msg = _READY.get(lang, _READY["en"])

            state.messages_history.append({"role": "assistant", "text": bot_msg})
            return ChatTurnResponse(
                session_id=state.session_id,
                bot_message=bot_msg,
                turn_count=state.turn_count,
                missing_fields=[],
                confirmation_card=card,
                safety_line=card.safety_line,
            )

        # 5. Ask ONLY the next missing field using active scenario pack questions
        next_missing = missing[0]
        q_dict = scenario.follow_up_questions.get(next_missing, {}) if scenario else {}
        question_text = q_dict.get(lang) or q_dict.get("en") or f"Please share your {next_missing}."

        state.messages_history.append({"role": "assistant", "text": question_text})
        return ChatTurnResponse(
            session_id=state.session_id,
            bot_message=question_text,
            turn_count=state.turn_count,
            missing_fields=missing,
            confirmation_card=None,
            safety_line=scenario_registry.get_safety_line("call_112", lang=lang),
        )


chat_intake_agent = ChatIntakeAgent()
