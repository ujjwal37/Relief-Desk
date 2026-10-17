"""Fixed 'While you wait' lines. Three short bullets, chosen by report type."""

from __future__ import annotations

from typing import Optional

RESCUE = ("status.tipHigh", "status.tipWires", "status.tipPhone")
MEDICAL = ("status.tipMedical1", "status.tipMedical2", "status.tipMedical3")
FOOD = ("status.tipFood1", "status.tipFood2", "status.tipFood3")
SHELTER = ("status.tipShelter1", "status.tipShelter2", "status.tipShelter3")
DOG = ("status.tipDog1", "status.tipDog2", "status.tipDog3")
DEFAULT = ("status.tipDefault1", "status.tipDefault2", "status.tipDefault3")


def _kind(incident_type: Optional[str]) -> str:
    return (incident_type or "").strip().lower().replace("-", "_").replace(" ", "_")


def wait_tips_for(incident_type: Optional[str]) -> list[str]:
    """Three i18n keys for a classified type, or for the type the reporter picked."""
    kind = _kind(incident_type)
    if kind in {"animal_attack", "dog", "dog_attack", "dog_bite"} or kind.startswith("dog"):
        return list(DOG)
    if kind in {"food", "food_water", "drinking_water"} or kind.startswith("food"):
        return list(FOOD)
    if kind in {"shelter"} or "shelter" in kind:
        return list(SHELTER)
    if kind in {"medical"} or kind.startswith("medic"):
        return list(MEDICAL)
    if kind in {"rescue", "flood", "water_rising"} or "flood" in kind:
        return list(RESCUE)
    return list(DEFAULT)


LIFE = "status.tipLife112"


def tips_for_request(req) -> list[str]:
    """Classified type once analysis is done. The picked type until then.
    A life threat in the reporter's words puts 'Call 112 now' first."""
    if req is None:
        return wait_tips_for(None)
    from app.tools.case_queue import life_phrase
    if life_phrase(getattr(req, "raw_text", None)) or life_phrase(getattr(req, "ai_translation", None)):
        kind = getattr(req, "type", None)
        value = getattr(kind, "value", kind)
        return [LIFE] + wait_tips_for(value if isinstance(value, str) else None)[:2]
    picked = getattr(req, "picked_type", None)
    if getattr(req, "analysis_status", "") == "analysing" and picked:
        return wait_tips_for(picked)
    kind = getattr(req, "type", None)
    value = getattr(kind, "value", kind)
    return wait_tips_for(value if isinstance(value, str) else None)
