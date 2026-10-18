"""AI working queue for one case.

The desk reads `ai_queue` on the case. Scoring and matching stay in the
deterministic tools. This module never calls Gemini itself. A recheck runs
only when the caller passes a client and the circuit is closed.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol

from app.models.firestore_models import AiQueueState, StoredRequest

logger = logging.getLogger("relief_desk.case_queue")

STEPS = ("read", "duplicates", "urgency", "team")
CAP_S = 45
READ_SLOTS = 2
RECHECK_GAP_S = 6.0  # about 10 cases a minute

# Life-threat pre-filter. Each pattern returns the words exactly as written (original script),
# which is what the card shows. English, Hindi, Hinglish, Malayalam and Manglish, several verb forms.
_NEG_ML = r"(?:\s*ഇല്ല|ില്ല|ുന്നില്ല)"
_LIFE_PATTERNS = [
    # English
    r"\b(?:not|isn'?t|stopped|stop|no longer|can'?t|cannot|unable to|difficulty|trouble)\s+breath(?:ing|e)\b",
    r"\bno pulse\b", r"\bunconscious\b", r"\bunresponsive\b", r"\bnot responding\b", r"\bpassed out\b", r"\bfainted\b",
    r"\b(?:lost|loss of)\s+consciousness\b", r"\bsemi-?conscious\b",
    r"\bdrown(?:ing|ed|s)?\b", r"\bheart attack\b", r"\bchest pain\b",
    r"\b(?:bleeding (?:a lot|heavily|badly|profusely|severely|non ?stop)|heavy bleeding|severe bleeding|profuse bleeding|severe blood loss|lot of blood|losing blood)\b",
    r"\b(?:profuse|excessive|continuous|uncontrolled)\s+bleeding\b",
    r"\btrapped under\b", r"\b(?:child|kid|baby|boy|girl|son|daughter)\b[^.]{0,20}\b(?:in|into|under) (?:the )?(?:water|flood)\b",
    r"\bswept away\b",
    # Ventilator or dialysis power cut (English)
    r"\b(?:ventilator|dialysis)\b[^.]{0,40}\b(?:power\s*(?:cut|outage|failure|loss|off)|no\s*(?:power|electricity)|electricity\s*(?:cut|off|loss)|current\s*(?:cut|off|loss)|generator\s*(?:failure|stopped))\b",
    r"\b(?:power\s*(?:cut|outage|failure|loss|off)|no\s*(?:power|electricity)|electricity\s*cut|current\s*(?:cut|off))\b[^.]{0,40}\b(?:ventilator|dialysis)\b",
    # Hindi (Devanagari)
    r"सा[ंँ]?स\s*(?:नहीं|नही|नहि|नहीँ|रुक|बंद|नहीं\s*ले)", r"बेहोश", r"बेहोशी", r"होश\s*(?:नहीं|खो)",
    r"(?:बच्चा|बच्ची|बेटा|बेटी|आदमी|औरत|कोई|पिताजी|पापा|मां|माँ|दादा|दादी)[^।.]{0,15}डूब\s*(?:रहा|रही|रहे|गया|गई|गयी|गए)",
    r"(?:सीने|छाती)\s*में\s*दर्द", r"(?:बहुत|ज़्यादा|ज्यादा)\s*खून", r"खून\s*बह", r"खून\s*(?:बह\s*रहा|निकल\s*रहा|रुक\s*नहीं)", r"(?:भारी|गंभीर)\s*रक्तस्राव",
    r"(?:बच्चा|बच्ची|बेटा|बेटी)[^।.]{0,15}पानी\s*में",
    r"(?:वेंटिलेटर|डायलिसिस)[^।.]{0,40}(?:बिजली\s*(?:गई|कटी|बंद|नहीं)|पावर\s*कट|करंट\s*गया|लाइट\s*गई)",
    r"(?:बिजली\s*(?:गई|कटी|बंद)|पावर\s*कट)[^।.]{0,40}(?:वेंटिलेटर|डायलिसिस)",
    # Hinglish
    r"\bsaa?n?s\s*(?:nahi|nahin|nai|ruk|band|nhi)\b", r"\bbehosh(?:i)?\b", r"\bhosh\s*(?:nahi|kho\s*diya|mein\s*nahi)\b",
    r"\b(?:bachcha|bacha|bachchi|beta|beti|aadmi|koi|papa|maa|dada|dadi)\b[^.]{0,15}\bdoo?b\s*(?:raha|rahi|rahe|gaya|gayi|gaye)\b",
    r"\b(?:seene|chhati|chati)\s*m(?:e|ei|ein|en)\s*dard\b", r"\b(?:bahut|zyada|bohot)\s*khoon\b", r"\bkhoon\s*(?:beh|nikal)\b",
    r"\b(?:bachcha|bacha|bachchi|beta|beti)\b[^.]{0,15}\bpaani\s*m(?:e|ein|en)\b",
    r"\b(?:ventilator|dialysis)\b[^.]{0,40}\b(?:bijli|current|light|power)\s*(?:chali\s*gayi|chala\s*gaya|nahi\s*hai|cut|band|off|gul|fail)\b",
    r"\b(?:bijli|current|light|power)\s*(?:chali\s*gayi|chala\s*gaya|cut|band)\b[^.]{0,40}\b(?:ventilator|dialysis)\b",
    # Malayalam
    r"(?:ശ്വാസ|ശ്വസി)[^\s.,!?]*(?:\s+[^\s.,!?]+)?" + _NEG_ML, r"ശ്വാസം\s*കിട്ടുന്നില്ല",
    r"ബോധ[^\s.,!?]*(?:\s*ഇല്ല|ില്ല|\s*കെട്ടു|ംകെട്ടു|ം\s*പോയി|ക്ഷയം)", r"അബോധാവസ്ഥ", r"അനക്ക[^\s.,!?]*(?:\s*ഇല്ല|ില്ല)",
    r"(?:കുട്ടി|കുഞ്ഞ്|ആൾ|അച്ഛൻ|അമ്മ|മോൻ|മോൾ|ചേട്ടൻ)[^.]{0,15}മുങ്ങ[^\s.,!?]*", r"മുങ്ങിത്താഴ[^\s.,!?]*", r"നെഞ്ച്?\s*വേദന|നെഞ്ചുവേദന",
    r"(?:ഒരുപാട്|ധാരാളം|കുറേ|കഠിനമായ|ഗുരുതരമായ|അമിതമായ)\s*(?:ചോര|രക്തം|രക്തസ്രാവം)", r"(?:ചോര|രക്തം)\s*(?:പോകുന്നു|വരുന്നു|ഒഴുകുന്നു|വാർന്നു|നിൽക്കുന്നില്ല)", r"രക്തസ്രാവം",
    r"(?:കുട്ടി|കുഞ്ഞ്|മോൻ|മോൾ)[^.]{0,15}വെള്ളത്തിൽ",
    r"(?:വെന്റിലേറ്റർ|ഡയാലിസിസ്|വെന്റിലേറ്ററ|ഡയാലിസിസ)[^.]{0,40}(?:കറന്റ്\s*(?:പോയി|ഇല്ല|കട്ട്|ഓഫ്)|കറന്റില്ല|വൈദ്യുതി\s*(?:ഇല്ല|പോയി|മുങ്ങി|തടസ്സപ്പെട്ടു)|പവർ\s*കട്ട്)",
    r"(?:കറന്റ്\s*പോയി|കറന്റില്ല|വൈദ്യുതി\s*ഇല്ല|പവർ\s*കട്ട്)[^.]{0,40}(?:വെന്റിലേറ്റർ|ഡയാലിസിസ്)",
    # Manglish
    r"\b(?:sh|s)waa?sam\s*(?:illa|kittunnilla)\b", r"\b(?:sh|s)wasamilla\b", r"\b(?:sh|s)wasikkunnilla\b", r"\bshwaasam\s*illa\b",
    r"\bbodham\s*(?:illa|kettu|poyi)\b", r"\bbodhamilla\b", r"\banakkam\s*illa\b", r"\banakkamilla\b",
    r"\b(?:kutti|kunju|achan|amma|mon|mol|chettan)\b[^.]{0,15}\bmung(?:i|unnu)\w*", r"\bmungi\s*thazhunnu\b", r"\bnenju\s*vedana\b",
    r"\b(?:chora|raktham)\s*(?:pokunnu|varunnu|ozhukunnu|nilkkunnilla)\b", r"\b(?:kooduthal|valare\s*kooduthal|othiri|kure|bhayankara)\s*(?:chora|raktham)\b", r"\brakthasravam\b",
    r"\b(?:kutti|kunju|mon|mol)\b[^.]{0,15}\bvellathil\b",
    r"\b(?:ventilator|dialysis)\b[^.]{0,40}\b(?:current\s*(?:poyi|illa|cut|off|kazhinju)|power\s*cut|electricity\s*poyi|currentilla)\b",
    r"\b(?:current\s*(?:poyi|illa|cut)|power\s*cut|currentilla)\b[^.]{0,40}\b(?:ventilator|dialysis)\b",
    # Oxygen running out and active labour (all languages)
    # English
    r"\boxygen\b[^.]{0,40}\b(?:running out|run out|runs out|ran out|finish(?:ing|ed|es)?|over|empty|emptied|almost (?:gone|empty)|exhausted|depleted|low)\b",
    r"\b(?:running out of|out of|no more|need urgent|lack of|low on)\s+oxygen\b",
    r"\b(?:oxygen\s+)?cylinder\b[^.]{0,35}\b(?:empty|emptied|finish(?:ing|ed|es)?|over|running out|run out)\b",
    r"\bempty\s+(?:oxygen\s+)?cylinder\b",
    r"\b(?:in|having|started|gone into) (?:active )?labou?r\b", r"\blabou?r pains?\b", r"\b(?:her )?water(?:s)? (?:has |have )?broken\b",
    # Hindi (Devanagari)
    r"ऑक्सीजन[^।.]{0,35}(?:खत्म|ख़त्म|खतम|समाप्त|नहीं|खाली|ना\s*के\s*बराबर)",
    r"(?:ऑक्सीजन\s+)?(?:सिलेंडर|सिलिंडर)[^।.]{0,35}(?:खत्म|ख़त्म|खतम|खाली)",
    r"प्रसव\s*पीड़ा", r"लेबर\s*पेन", r"दर्द\s*शुरू[^।.]{0,15}(?:डिलीवरी|प्रसव)",
    # Hinglish
    r"\boxygen\b[^.]{0,35}\b(?:khatam|khatm|khtm|khatma|khali|nahi\s*bacha|samapt|chala\s*gaya|ruk\s*gaya)\b",
    r"\b(?:oxygen\s+)?(?:cylinder|silendar)\b[^.]{0,35}\b(?:khatam|khatm|khtm|khatma|khali)\b",
    r"\b(?:khatam|khali)\s*(?:oxygen|cylinder)\b",
    r"\b(?:labou?r|delivery)\s*(?:pain|dard)\b", r"\bprasav\s*(?:pida|peeda|dard)\b",
    # Malayalam
    r"ഓക്സിജൻ[^.]{0,35}(?:തീർ|തീരാ|തീരുന്നു|തീരാറായി|തീരാൻ|ഇല്ല|കഴിഞ്ഞ|കാലി|അവസാനിക്കാറായ)",
    r"(?:ഓക്സിജൻ\s+)?(?:സിലിണ്ടർ|സിലിണ്ടറ)[^.]{0,35}(?:തീർ|തീരാ|തീരുന്നു|തീരാറായി|തീരാൻ|കഴിഞ്ഞ|കാലി)",
    r"പ്രസവ\s*വേദന|പ്രസവവേദന",
    # Manglish
    r"\boxygen\b[^.]{0,35}\b(?:theeran|theerunnu|theernnu|theerarayi|theerukayanu|theerapoyi|theeraru|kazhinju|illa|kaali|empty)\b",
    r"\b(?:oxygen\s+)?(?:cylinder|silindar)\b[^.]{0,35}\b(?:theeran|theerunnu|theernnu|theerarayi|kazhinju|illa|kaali|empty)\b",
    r"\b(?:theeran|theerunnu|theernnu|theerarayi)\s*(?:aayi|pokunnu)?\s*oxygen\b",
    r"\bprasava\s*vedana\b",
]
_LIFE_RE = [re.compile(p, re.IGNORECASE) for p in _LIFE_PATTERNS]
# "not breathing well yesterday, now ok": a recovered past state is not a life threat.
_RECOVERED = re.compile(r"\b(?:now (?:ok|okay|fine|better|breathing)|is fine now|recovered)\b|ഇപ്പോൾ\s*കുഴപ്പമില്ല|अब ठीक", re.IGNORECASE)


class ReviewClient(Protocol):
    def review(self, case: StoredRequest) -> dict:
        """Return proposed field values. Tests pass a fake. No network here."""


class RecheckPacer:
    def __init__(self, gap: float = RECHECK_GAP_S) -> None:
        self.gap = gap
        self.last: Optional[float] = None

    def allow(self, now: float) -> bool:
        if self.last is not None and (now - self.last) < self.gap:
            return False
        self.last = now
        return True


_PACER = RecheckPacer()


def life_phrase(text: str | None) -> Optional[str]:
    """The keyword pre-filter. Returns the matched words, or None."""
    if not text:
        return None
    if _RECOVERED.search(text):
        return None
    for pattern in _LIFE_RE:
        hit = pattern.search(text)
        if hit:
            return hit.group(0).strip()
    return None


_WATER_WORDS = re.compile(
    r"water|flood|drown|boat|roof|jetty|river|canal|വെള്ള|മുങ്ങ|ബോട്ട്|vellam|पानी|बाढ़|डूब|नाव|paani|pani|baadh|doob|naav",
    re.I,
)


def life_pick_kind(req: StoredRequest, text: str | None = None) -> str:
    """Boat when water is part of the report, otherwise the nearest medical team (ambulance)."""
    words = " ".join(x for x in (text, req.raw_text, req.ai_translation) if x)
    hazard = getattr(req.hazard, "value", req.hazard) or ""
    if _WATER_WORDS.search(words) or hazard in ("water_rising", "stranded"):
        return "boat"
    return "medical"


def promote_life_threat(req: StoredRequest, text: str | None) -> bool:
    """Second path: the model's English translation hits a trigger the original words missed."""
    queue = req.ai_queue
    if queue is None or "lifeThreat" in (queue.flags or []):
        return False
    phrase = life_phrase(text)
    if not phrase:
        return False
    queue.flags = list(queue.flags or []) + ["lifeThreat"]
    if not queue.life_phrase:
        queue.life_phrase = phrase
    queue.life_pick = life_pick_kind(req, text)
    return True


def mark_seed_life_threats(cases: Iterable[StoredRequest]) -> list[str]:
    """Seeded and reloaded cases go through the same keyword lane as live intake."""
    hit: list[str] = []
    for req in cases:
        status = getattr(req.status, "value", req.status)
        if status in ("dispatched", "completed", "cancelled"):
            continue
        text = " ".join(x for x in (req.raw_text, req.ai_translation) if x)
        phrase = life_phrase(req.raw_text) or life_phrase(req.ai_translation)
        if not phrase:
            continue
        if req.ai_queue is None:
            req.ai_queue = AiQueueState(
                status="ready",
                steps={step: "done" for step in STEPS},
                engine="rules",
                flags=["lifeThreat"],
                life_phrase=phrase,
            )
            req.ai_queue.life_pick = life_pick_kind(req, text)
        elif "lifeThreat" not in (req.ai_queue.flags or []):
            req.ai_queue.flags = list(req.ai_queue.flags or []) + ["lifeThreat"]
            req.ai_queue.life_phrase = req.ai_queue.life_phrase or phrase
            req.ai_queue.life_pick = life_pick_kind(req, text)
        hit.append(req.id)
    return hit


def is_life_threat(req: StoredRequest) -> bool:
    queue = req.ai_queue
    return bool(queue and "lifeThreat" in (queue.flags or []))


def steps_done(req: StoredRequest) -> bool:
    queue = req.ai_queue
    if queue is None:
        return True
    return all(queue.steps.get(step) == "done" for step in STEPS)


def approve_blocked(req: StoredRequest) -> bool:
    """True while the four steps are still running and rules have not taken over."""
    if req.ai_queue is None:
        return False
    if steps_done(req):
        return False
    if "timedOut" in (req.ai_queue.flags or []):
        return False
    return req.analysis_status == "analysing"


def _now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _parse(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def elapsed_seconds(queue: AiQueueState, now: datetime | None = None) -> int:
    try:
        started = _parse(queue.started_at)
    except ValueError:
        return 0
    return max(0, int((_now(now) - started).total_seconds()))


def _live() -> bool:
    from app.llm.client import llm_client
    return bool(llm_client.gemini_live())


def _paused() -> bool:
    from app.llm.client import llm_client
    return bool(llm_client.guard.circuit_open())


def begin_case(req: StoredRequest, text: str | None, *, now: datetime | None = None, others: Iterable[StoredRequest] | None = None) -> AiQueueState:
    """Attach queue state at intake, before any model call."""
    moment = _now(now)
    phrase = life_phrase(text or req.raw_text)
    paused = _paused()
    live = _live() and not paused
    steps = {step: "pending" for step in STEPS}
    flags: list[str] = []
    if paused:
        flags.append("paused")
    engine = "gemini" if live else "rules"
    status = "queued"
    step: Optional[str] = None
    queue_pos: Optional[int] = None
    if phrase:
        flags.append("lifeThreat")
        status = "ready"
        steps["read"] = "active"
        step = "read"
    else:
        busy = 0
        for other in others or []:
            other_q = other.ai_queue
            if other.id == req.id or other_q is None:
                continue
            if other_q.status == "processing" and "lifeThreat" not in (other_q.flags or []):
                busy += 1
        if busy < READ_SLOTS:
            status = "processing"
            steps["read"] = "active"
            step = "read"
        else:
            queue_pos = busy
    req.ai_queue = AiQueueState(
        status=status,
        step=step,
        steps=steps,
        engine=engine,
        started_at=moment.isoformat(),
        elapsed_s=0,
        flags=flags,
        queue_pos=queue_pos,
        life_phrase=phrase,
        place_unverified=bool(phrase),
    )
    if phrase:
        req.ai_queue.life_pick = life_pick_kind(req, text)
    return req.ai_queue


def note_progress(req: StoredRequest, done: Iterable[str] = (), active: str | None = None) -> None:
    queue = req.ai_queue
    if queue is None:
        return
    for step in done:
        if step in queue.steps:
            queue.steps[step] = "done"
    if active and active in queue.steps and queue.steps[active] != "done":
        queue.steps[active] = "active"
        queue.step = active
        if "lifeThreat" not in (queue.flags or []):
            queue.status = "processing"
            queue.queue_pos = None


def abandon_if_capped(req: StoredRequest, now: datetime | None = None) -> bool:
    """At 45s, rules finish the case. Does not call a model."""
    queue = req.ai_queue
    if queue is None:
        return False
    if "timedOut" in (queue.flags or []) and steps_done(req):
        return True
    if steps_done(req) and queue.status == "ready":
        return False
    if elapsed_seconds(queue, now) < CAP_S:
        queue.elapsed_s = elapsed_seconds(queue, now)
        return False
    for step in STEPS:
        queue.steps[step] = "done"
    queue.status = "ready"
    queue.step = None
    queue.queue_pos = None
    queue.engine = "rules"
    queue.elapsed_s = elapsed_seconds(queue, now)
    if "timedOut" not in queue.flags:
        queue.flags = list(queue.flags) + ["timedOut"]
    if "paused" in queue.flags and queue.engine == "gemini":
        queue.engine = "rules"
    req.analysis_status = "complete"
    return True


def mark_steps_done(req: StoredRequest, *, used_gemini: bool) -> None:
    """The pipeline finished. The engine stays rules when Gemini did not run."""
    queue = req.ai_queue
    if queue is None:
        return
    if "timedOut" in (queue.flags or []) or "paused" in (queue.flags or []):
        if queue.engine != "gemini_rechecked":
            queue.engine = "rules"
    elif used_gemini:
        queue.engine = "gemini"
    elif queue.engine != "gemini_rechecked":
        queue.engine = "rules"
    for step in STEPS:
        queue.steps[step] = "done"
    queue.status = "ready"
    queue.step = None
    queue.queue_pos = None


def _open_for_line(req: StoredRequest) -> bool:
    queue = req.ai_queue
    if queue is None or is_life_threat(req):
        return False
    if "timedOut" in (queue.flags or []) or steps_done(req):
        return False
    return queue.status in ("queued", "processing")


def place_in_line(cases: Iterable[StoredRequest], *, slots: int = READ_SLOTS) -> None:
    """Life-threat cases are not in line. The first slots are reading; the rest are queued."""
    waiting = [req for req in cases if _open_for_line(req)]
    waiting.sort(key=lambda req: req.ai_queue.started_at if req.ai_queue else "")
    for index, req in enumerate(waiting):
        queue = req.ai_queue
        if queue is None:
            continue
        if index < slots:
            queue.status = "processing"
            queue.queue_pos = None
            if queue.step is None:
                queue.step = "read"
                if queue.steps.get("read") == "pending":
                    queue.steps["read"] = "active"
        else:
            queue.status = "queued"
            queue.queue_pos = index - slots + 1
            queue.step = None


def refresh_queue(cases: Iterable[StoredRequest], *, now: datetime | None = None) -> list[str]:
    """Live elapsed, the 45s cap, and queue positions. Returns ids the cap closed."""
    rows = list(cases)
    moment = _now(now)
    closed: list[str] = []
    for req in rows:
        if req.ai_queue is None:
            continue
        already = "timedOut" in (req.ai_queue.flags or [])
        if abandon_if_capped(req, moment):
            mark_steps_done(req, used_gemini=False)
            if not already:
                closed.append(req.id)
        else:
            req.ai_queue.elapsed_s = elapsed_seconds(req.ai_queue, moment)
    place_in_line(rows)
    return closed


def _needs_recheck(req: StoredRequest) -> bool:
    queue = req.ai_queue
    if queue is None or queue.engine != "rules":
        return False
    flags = set(queue.flags or [])
    if not ({"timedOut", "paused"} & flags):
        return False
    return True


def _diff(req: StoredRequest, proposed: dict | None) -> dict[str, Any]:
    if not proposed:
        return {}
    changed: dict[str, Any] = {}
    for field in ("people_count", "place_text", "urgency_score", "type"):
        if field not in proposed:
            continue
        current = getattr(req, field, None)
        if hasattr(current, "value"):
            current = current.value
        incoming = proposed[field]
        if hasattr(incoming, "value"):
            incoming = incoming.value
        if incoming != current:
            changed[field] = {"from": current, "to": incoming}
    return changed


def recheck_next(
    cases: Iterable[StoredRequest],
    *,
    client: ReviewClient | None,
    now: float,
    circuit_closed: bool,
    pacer: RecheckPacer | None = None,
) -> Optional[str]:
    """Recheck one rules-fallback case. Critical (highest urgency) first.

    Returns the case id, or None when nothing is due, the circuit is open,
    or the pace has not elapsed. `client` is required; this never opens a
    network connection on its own.
    """
    if client is None or not circuit_closed:
        return None
    due = [req for req in cases if _needs_recheck(req)]
    if not due:
        return None
    due.sort(key=lambda req: (-(req.urgency_score or 0), req.created_at or ""))
    gate = pacer or _PACER
    if not gate.allow(now):
        return None
    target = due[0]
    proposed = client.review(target)
    queue = target.ai_queue
    if queue is None:
        return None
    if not (isinstance(proposed, dict) and proposed):
        # Gemini gave nothing usable (fallback or bad JSON): the label stays rules, never "Gemini rechecked".
        return None
    queue.engine = "gemini_rechecked"
    diff = _diff(target, proposed if isinstance(proposed, dict) else None)
    queue.recheck_diff = diff or None
    return target.id


def recheck_if_live(cases: Iterable[StoredRequest], *, now: float | None = None) -> Optional[str]:
    """Production hook. With no live Gemini key this returns before any call."""
    from app.llm.client import llm_client

    rows = list(cases)
    if not any(_needs_recheck(req) for req in rows):
        return None
    if not llm_client.gemini_live() or llm_client.guard.circuit_open():
        return None
    try:
        return recheck_next(
            rows,
            client=_LiveReview(),
            now=time.time() if now is None else now,
            circuit_closed=True,
            pacer=_PACER,
        )
    except Exception:
        logger.exception("Gemini recheck did not run")
        return None


class _LiveReview:
    """One paced Gemini read. Used only when gemini_live() is already true."""

    def review(self, case: StoredRequest) -> dict:
        import json
        from app.llm.client import llm_client

        prompt = (
            "Compare this report with the extracted fields. "
            "Reply with JSON object keys people_count, place_text, urgency_score only. "
            "Copy numbers that are already in the report. Do not invent any.\n"
            f"Report: {(case.raw_text or '')[:500]}\n"
            f"people_count: {case.people_count}\nplace_text: {case.place_text}\nurgency_score: {case.urgency_score}"
        )
        raw = llm_client.generate(prompt, system_instruction="Return JSON only. Do not give advice.")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        keep = {}
        if isinstance(data.get("people_count"), int):
            keep["people_count"] = data["people_count"]
        if isinstance(data.get("place_text"), str):
            keep["place_text"] = data["place_text"]
        if isinstance(data.get("urgency_score"), (int, float)) and not isinstance(data.get("urgency_score"), bool):
            keep["urgency_score"] = data["urgency_score"]
        return keep
