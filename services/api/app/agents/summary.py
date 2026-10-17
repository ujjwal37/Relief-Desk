"""Summaries stay inside what the report actually said.

A model must not rename a condition ("severe diabetic emergency" is not
"acute insulin shock") and a chat summary is the report, not the last reply.
"""
from __future__ import annotations

import re
from typing import List, Optional

# Phrases a summary may use only when the citizen's words already contain them.
_CONDITIONS = (
    "acute insulin shock",
    "insulin shock",
    "hypoglycemic shock",
    "diabetic ketoacidosis",
    "diabetic coma",
    "hypoglycemia",
    "hyperglycemia",
    "heart attack",
    "cardiac arrest",
    "myocardial infarction",
    "septic shock",
    "anaphylactic shock",
    "anaphylaxis",
    "stroke",
    "sepsis",
    "pneumonia",
    "cholera",
    "dengue",
    "malaria",
    "covid",
    "fracture",
    "concussion",
    "miscarriage",
    "eclampsia",
    "pre-eclampsia",
    "preeclampsia",
)

_BARE_REPLY = re.compile(
    r"^(?:no|yes|ok|okay|y|n|nahi|nahin|haan|han|नहीं|हाँ|ഇല്ല|അല്ല|അതെ)\.?$",
    re.IGNORECASE,
)


def unstated_conditions(source: str, summary: str) -> List[str]:
    """Condition phrases in the summary that the report never used."""
    src = (source or "").lower()
    written = (summary or "").lower()
    found: List[str] = []
    for phrase in _CONDITIONS:
        if phrase in written and phrase not in src:
            found.append(phrase)
    return found


def guard_summary(source: str, summary: str) -> str:
    """Keep the summary, or the report itself when the summary adds a condition."""
    source_clean = " ".join((source or "").split())
    candidate = " ".join((summary or "").split())
    if not candidate:
        return source_clean[:800]
    if unstated_conditions(source_clean, candidate):
        return source_clean[:800]
    return candidate


_QUICK_REPLY = re.compile(
    r"^(?:none of these|no|yes|ok|okay|not sure|i am not sure\b.*|i'?m not sure\b.*|"
    r"mujhe (?:nahi|nahin) pata\b.*|pata nahi\b.*|how many people\b.*)$",
    re.IGNORECASE,
)


def short_faithful_summary(report_text: str) -> str:
    """One short line from what the citizen reported. Quick replies are not the summary."""
    lines = [line.strip() for line in (report_text or "").splitlines() if line.strip()]
    kept = [line for line in lines if not _QUICK_REPLY.match(line) and not _BARE_REPLY.match(line)]
    text = " ".join(kept or lines)
    text = " ".join(text.split())
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?।])\s+", text)
    summary = parts[0]
    if len(summary) < 40 and len(parts) > 1:
        summary = " ".join(parts[:2])
    if len(summary) > 180:
        cut = summary[:177].rsplit(" ", 1)[0]
        summary = (cut or summary[:177]) + "…"
    return summary


def summary_from_report(report_text: str, card_summary: Optional[str] = None) -> str:
    """Build the case summary from the report, never from a lone last chat answer."""
    report = " ".join((report_text or "").split())
    card = " ".join((card_summary or "").split())
    lines = [line.strip() for line in (report_text or "").splitlines() if line.strip()]
    chosen = card or report
    if not chosen:
        return ""
    last = lines[-1] if lines else ""
    bare_last = bool(lines) and (_BARE_REPLY.match(last) or len(last) <= 3)
    if _BARE_REPLY.match(chosen) or (bare_last and chosen == last and len(lines) >= 2 and len(chosen) < len(report)):
        chosen = report
    if any(_QUICK_REPLY.match(line) or _BARE_REPLY.match(line) for line in (chosen.splitlines() or [chosen])):
        chosen = short_faithful_summary(chosen)
    return guard_summary(report or chosen, chosen)
