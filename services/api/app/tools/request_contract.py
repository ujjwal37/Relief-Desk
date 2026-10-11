"""Single Request shape for chat confirmation and the form path.

Ids and timestamps are applied later by storage. This dict is the contract.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

VULNERABLE_KEYS = ("child", "elderly", "disabled", "pregnant", "medical_need")


def _vulnerable(raw: Optional[Mapping[str, Any]]) -> Dict[str, bool]:
    source = raw or {}
    return {key: bool(source.get(key, False)) for key in VULNERABLE_KEYS}


def canonical_request_dict(
    *,
    incident_type: str,
    place_text: Optional[str],
    people_count: Optional[int],
    vulnerable: Optional[Mapping[str, Any]],
    hazard: str,
    summary: str,
    lang: str,
    scenario_id: str,
    lat: Optional[float],
    lng: Optional[float],
) -> Dict[str, Any]:
    return {
        "hazard": hazard,
        "lang": lang,
        "lat": None if lat is None else round(float(lat), 6),
        "lng": None if lng is None else round(float(lng), 6),
        "pack_id": scenario_id,
        "people_count": people_count,
        "place_text": place_text,
        "summary": summary,
        "type": incident_type,
        "vulnerable": _vulnerable(vulnerable),
    }


def canonical_request_json(**kwargs: Any) -> str:
    return json.dumps(canonical_request_dict(**kwargs), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
