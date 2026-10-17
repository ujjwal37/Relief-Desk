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
from app.agents.summary import short_faithful_summary
from app.tools.nlu_rules import (
    extract_place,
    infer_incident_type,
    is_nobody_stranded,
    known_place,
    need_from_reply,
    parse_people_reply,
    people_count,
    place_from_answer,
    place_is_usable,
    water_from_answer,
    water_stated,
)
from app.tools.trust import hoax_reason_for

logger = logging.getLogger("relief_desk.chat_intake")


def _script_lang(text: str) -> Optional[str]:
    """Malayalam or Devanagari in the report picks the question language."""
    if re.search(r"[\u0D00-\u0D7F]", text or ""):
        return "ml"
    if re.search(r"[\u0900-\u097F]", text or ""):
        return "hi"
    return None

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

_NEED_Q = {
    "en": "What do you need? Rescue, medical help, food, or shelter?",
    "hi": "आपको किस मदद की ज़रूरत है? बचाव, चिकित्सा, भोजन या आश्रय?",
    "hinglish": "Aapko kya chahiye? Rescue, medical, khana ya shelter?",
    "ml": "നിങ്ങൾക്ക് എന്ത് സഹായമാണ് വേണ്ടത്? രക്ഷാപ്രവർത്തനം, മെഡിക്കൽ, ഭക്ഷണം അല്ലെങ്കിൽ അഭയം?",
}

_HOAX_HELD = {
    "en": "This message looks like spam or a hoax. It is held for a coordinator to review. Nothing is sent until a person checks it.",
    "hi": "यह संदेश स्पैम या धोखा लगता है। इसे समन्वयक की जाँच तक रोक दिया गया है। कोई मदद तब तक नहीं भेजी जाएगी।",
    "hinglish": "Yeh message spam ya hoax lagta hai. Coordinator ke review tak ise rok diya gaya hai. Tab tak kuch nahi bheja jayega.",
    "ml": "ഈ സന്ദേശം സ്പാം അല്ലെങ്കിൽ തട്ടിപ്പ് ആണെന്ന് തോന്നുന്നു. ഒരു കോർഡിനേറ്റർ പരിശോധിക്കുന്നതുവരെ ഇത് നിർത്തിവെച്ചിരിക്കുന്നു.",
}

# Short close, with no pipe summary and no raw hazard or type keys.
_READY = {
    "en": "Details are ready. Review the card below and tap Send.",
    "hi": "विवरण तैयार है। नीचे दिए कार्ड की जाँच करें और भेजें।",
    "hinglish": "Details ready hain. Neeche wala card check karke bhej dijiye.",
    "ml": "വിവരങ്ങൾ തയ്യാർ. താഴെയുള്ള കാർഡ് പരിശോധിച്ച് അയയ്ക്കുക.",
}


_LIFE_112 = {
    "en": "This sounds life-threatening. Call 112 now.",
    "hi": "यह जान का खतरा लगता है। अभी 112 पर कॉल करें।",
    "hinglish": "Yeh jaan ka khatra lagta hai. Abhi 112 pe call karein.",
    "ml": "ഇത് ജീവന് ഭീഷണിയാണ്. ഇപ്പോൾ തന്നെ 112 വിളിക്കുക.",
    "manglish": "Ithu jeevanu bheeshaniyanu. Ippol thanne 112 vilikkuka.",
}


_NEED_WORDS = {
    "en": {"rescue": "Rescue needed", "medical": "Medical help needed", "food": "Food and water needed", "shelter": "Shelter needed", "info": "Information"},
    "hi": {"rescue": "बचाव चाहिए", "medical": "चिकित्सा मदद चाहिए", "food": "खाना-पानी चाहिए", "shelter": "आश्रय चाहिए", "info": "जानकारी"},
    "hinglish": {"rescue": "Bachav chahiye", "medical": "Medical madad chahiye", "food": "Khana-paani chahiye", "shelter": "Aashray chahiye", "info": "Jaankari"},
    "ml": {"rescue": "രക്ഷാപ്രവർത്തനം വേണം", "medical": "വൈദ്യസഹായം വേണം", "food": "ഭക്ഷണവും വെള്ളവും വേണം", "shelter": "അഭയം വേണം", "info": "വിവരം"},
}
_PEOPLE_WORD = {"en": "{n} people", "hi": "{n} लोग", "hinglish": "{n} log", "ml": "{n} പേർ"}


def _slot_summary(kind, people, place, lang: str) -> str:
    """A short summary in the reporter's language, built from what they told us (never the transcript)."""
    code = lang if lang in _NEED_WORDS else ("ml" if lang == "manglish" else "en")
    value = getattr(kind, "value", kind) or ""
    need = _NEED_WORDS[code].get(value)
    if not need or value == "info":
        # Information reports keep the reporter's own words ("nobody is stranded").
        return ""
    parts = [need]
    if people:
        parts.append(_PEOPLE_WORD[code].format(n=people))
    if place:
        parts.append(str(place)[:60])
    return " · ".join(parts)


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
    likely_hoax: bool = False
    hoax_reason: Optional[str] = None
    held: bool = False
    # Life threat: the chat stopped asking and the reporter sees Call 112 first.
    life_threat: bool = False
    life_phrase: Optional[str] = None
    # The reporter's first message, word for word, and their later answers kept apart from it.
    original_text: str = ""
    answers: List[str] = Field(default_factory=list)


class ChatTurnState(BaseModel):
    session_id: str
    scenario_id: str = "flood"
    language: str = "en"
    turn_count: int = 0
    extracted_so_far: ExtractedRequest = Field(default_factory=ExtractedRequest)
    messages_history: List[Dict[str, str]] = Field(default_factory=list)
    is_complete: bool = False
    confirmation_card: Optional[ConfirmationCardData] = None
    awaiting_slot: Optional[str] = None
    slot_location: bool = False
    slot_people: bool = False
    slot_need: bool = False
    slot_water: bool = False
    people_unknown: bool = False


class ChatTurnResponse(BaseModel):
    session_id: str
    bot_message: str
    turn_count: int
    missing_fields: List[str]
    confirmation_card: Optional[ConfirmationCardData] = None
    safety_line: Optional[str] = None
    likely_hoax: bool = False
    hoax_reason: Optional[str] = None
    held: bool = False


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
        # A Malayalam or Hindi report is asked about in that language, even if the UI is English.
        script = _script_lang(user_message)
        if script:
            lang = script
            state.language = script

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

        full_text = "\n".join(
            message["text"] for message in state.messages_history if message.get("role") == "user" and message.get("text")
        )
        hoax_reason = hoax_reason_for(full_text)
        type_before = state.extracted_so_far.type
        self._fill_slots(state, user_message, full_text, lang, lang_override, location_pin)
        # One try per question. A reply that does not fill the slot moves on.
        self._give_up_unanswered(state)

        # A rescue or medical report stays one: a later answer (a vague place) never turns it into Information.
        team_need = type_before in (IncidentType.RESCUE, IncidentType.MEDICAL, IncidentType.FOOD, IncidentType.SHELTER)
        if team_need and state.extracted_so_far.type == IncidentType.INFO:
            state.extracted_so_far.type = type_before
        # A life threat in any language stops the questions at once: Call 112 and send now.
        # Same detector as live intake and the seeded queue (case_queue.life_phrase).
        from app.tools.case_queue import life_phrase
        if not hoax_reason and life_phrase(full_text):
            for slot in self._missing_slots(state):
                setattr(state, f"slot_{'people' if slot == 'people_count' else 'need' if slot == 'need' else slot}", True)
                if slot == "people_count":
                    state.people_unknown = state.extracted_so_far.people.count is None
            return self._finish(state, scenario, lang, full_text, hoax_reason)
        if is_nobody_stranded(full_text) and not (team_need and not is_nobody_stranded(user_message)):
            self._mark_nobody(state)
            return self._finish(state, scenario, lang, full_text, hoax_reason)

        # A scam is filed once, held, and never turned into a follow-up whose last word becomes the summary.
        if hoax_reason or not self._missing_slots(state) or state.turn_count >= 4:
            return self._finish(state, scenario, lang, full_text, hoax_reason)

        missing = self._missing_slots(state)
        question = self._question_for(scenario, missing[0], lang)
        state.awaiting_slot = missing[0]
        state.messages_history.append({"role": "assistant", "text": question})
        return ChatTurnResponse(
            session_id=state.session_id,
            bot_message=question,
            turn_count=state.turn_count,
            missing_fields=missing,
            confirmation_card=None,
            safety_line=scenario_registry.get_safety_line("call_112", lang=lang),
        )

    def _fill_slots(
        self,
        state: ChatTurnState,
        message: str,
        full_text: str,
        lang: str,
        lang_override: Optional[str],
        location_pin: Optional[Dict[str, float]],
    ) -> None:
        """Read slots from the whole report, then from the answer to the question we just asked."""
        extracted_turn = intake_agent.parse_report(message, language_hint=lang)
        current = state.extracted_so_far
        if extracted_turn.language and not lang_override:
            state.language = extracted_turn.language.value
        for flag in ("child", "elderly", "disabled", "pregnant", "medical_need"):
            if getattr(extracted_turn.vulnerable, flag):
                setattr(current.vulnerable, flag, True)

        if not state.slot_location:
            place = place_from_answer(message) if state.awaiting_slot == "location" else None
            if not place:
                place = extract_place(full_text)
            named = known_place(full_text)
            if named and (not place or named.lower() not in place.lower()):
                place = named
            if not place and state.awaiting_slot == "location":
                # Keep what the reporter typed for "where are you?" even when it is vague; the desk verifies it.
                typed = (message or "").strip(" .,!?\n\t")
                status, _n = parse_people_reply(typed)
                if 3 <= len(typed) and status != "unknown" and not re.fullmatch(r"[\d\s?.!-]+", typed):
                    place = typed[:60]
            if place and (place_is_usable(place) or state.awaiting_slot == "location"):
                current.place_text = place
                state.slot_location = True
            elif location_pin and location_pin.get("lat") is not None and location_pin.get("lng") is not None and not current.place_text:
                current.place_text = f"Pin ({location_pin['lat']:.4f}, {location_pin['lng']:.4f})"
                state.slot_location = True

        if not state.slot_people:
            status, count = ("absent", None)
            if state.awaiting_slot == "people_count":
                status, count = parse_people_reply(message)
            if status == "unknown":
                current.people.count = None
                state.slot_people = True
                state.people_unknown = True
            elif status == "count" and count:
                current.people.count = count
                state.slot_people = True
                state.people_unknown = False
            else:
                counted = people_count(full_text)
                if counted:
                    current.people.count = counted
                    state.slot_people = True
                    state.people_unknown = False
        elif state.awaiting_slot == "people_count":
            # A filled slot is never overwritten by a later shrug, and never asked again.
            status, count = parse_people_reply(message)
            if status == "count" and count and not state.people_unknown:
                current.people.count = count

        kind = infer_incident_type(full_text)
        if not kind and state.awaiting_slot == "need":
            kind = need_from_reply(message)
        if kind == "info" and current.type in (IncidentType.RESCUE, IncidentType.MEDICAL, IncidentType.FOOD, IncidentType.SHELTER):
            kind = None  # never downgrade a team need to Information on a later turn
        if kind and kind != "other":
            current.type = IncidentType(kind)
            state.slot_need = True
        elif state.awaiting_slot == "need" and kind:
            current.type = IncidentType(kind)
            state.slot_need = True

        stated = water_stated(full_text)
        if not stated and state.awaiting_slot == "water":
            stated = water_from_answer(message)
        if stated and not state.slot_water:
            state.slot_water = True
            if stated == "rising" and current.hazard != HazardType.WATER_RISING:
                current.hazard = HazardType.WATER_RISING
            elif stated == "none" and current.hazard in (HazardType.UNKNOWN, HazardType.NONE):
                current.hazard = HazardType.NONE
            elif stated not in ("rising", "none") and current.hazard == HazardType.UNKNOWN:
                current.hazard = HazardType.WATER_RISING
        # A junk place reopens the question. A question already given up on stays closed.
        if current.place_text and not place_is_usable(current.place_text) and not state.slot_location:
            current.place_text = None
            state.slot_location = False
        if current.people.count is not None and current.people.count <= 0:
            current.people.count = None

    def _give_up_unanswered(self, state: ChatTurnState) -> None:
        slot = state.awaiting_slot
        if not slot or slot not in self._missing_slots(state):
            return
        current = state.extracted_so_far
        if slot == "location":
            state.slot_location = True
            if not place_is_usable(current.place_text):
                current.place_text = None
        elif slot == "people_count":
            state.slot_people = True
            state.people_unknown = True
        elif slot == "need":
            state.slot_need = True
        elif slot == "water":
            state.slot_water = True

    def _mark_nobody(self, state: ChatTurnState) -> None:
        current = state.extracted_so_far
        current.type = IncidentType.INFO
        current.hazard = HazardType.NONE
        current.people.count = None
        state.slot_need = True
        state.slot_people = True
        state.people_unknown = True
        state.slot_water = True
        if not place_is_usable(current.place_text):
            current.place_text = None

    def _missing_slots(self, state: ChatTurnState) -> List[str]:
        missing: List[str] = []
        if not state.slot_location:
            missing.append("location")
        if not state.slot_people:
            missing.append("people_count")
        if not state.slot_need:
            missing.append("need")
        if not state.slot_water:
            missing.append("water")
        return missing

    def _question_for(self, scenario, slot: str, lang: str) -> str:
        if slot == "need":
            return _NEED_Q.get(lang) or _NEED_Q["en"]
        key = "hazard" if slot == "water" else slot
        questions = scenario.follow_up_questions.get(key, {}) if scenario else {}
        return questions.get(lang) or questions.get("en") or f"Please share your {slot}."

    def _finish(self, state: ChatTurnState, scenario, lang: str, full_text: str, hoax_reason: Optional[str]) -> ChatTurnResponse:
        state.is_complete = True
        state.awaiting_slot = None
        current = state.extracted_so_far
        people = current.people.count if state.slot_people and not state.people_unknown else None
        if people is not None and people <= 0:
            people = None
        summary = (_slot_summary(current.type, people, current.place_text, lang) if not hoax_reason else "") or short_faithful_summary(full_text)
        quiet = bool(hoax_reason) or current.type == IncidentType.INFO
        if quiet:
            line = scenario_registry.get_safety_line("call_112", lang=lang)
            bot_msg = f"{_HOAX_HELD.get(lang, _HOAX_HELD['en'])} {line}".strip() if hoax_reason else _READY.get(lang, _READY["en"])
        else:
            line = pack_notice(scenario, lang)
            bot_msg = _READY.get(lang, _READY["en"])
        from app.tools.case_queue import life_phrase
        phrase = None if hoax_reason else life_phrase(full_text)
        if phrase:
            # A life threat in any language: call 112 now comes first, in the reporter's language.
            line = scenario_registry.get_safety_line("call_112", lang=lang)
            bot_msg = _LIFE_112.get(lang, _LIFE_112["en"])
        said = [m["text"] for m in state.messages_history if m.get("role") == "user" and m.get("text")]
        card = ConfirmationCardData(
            incident_type=current.type.value,
            place_text=current.place_text or "",
            people_count=people,
            vulnerable=current.vulnerable.model_dump(),
            hazard=current.hazard.value,
            summary=summary,
            safety_line=line,
            ready_to_submit=True,
            likely_hoax=bool(hoax_reason),
            hoax_reason=hoax_reason,
            held=bool(hoax_reason),
            life_threat=bool(phrase),
            life_phrase=phrase,
            original_text=said[0] if said else "",
            answers=said[1:],
        )
        state.confirmation_card = card
        state.messages_history.append({"role": "assistant", "text": bot_msg})
        return ChatTurnResponse(
            session_id=state.session_id,
            bot_message=bot_msg,
            turn_count=state.turn_count,
            missing_fields=[],
            confirmation_card=card,
            safety_line=line,
            likely_hoax=bool(hoax_reason),
            hoax_reason=hoax_reason,
            held=bool(hoax_reason),
        )


chat_intake_agent = ChatIntakeAgent()
