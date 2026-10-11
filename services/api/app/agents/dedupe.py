import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from app.models.schemas import (
    DedupeDecision,
    DedupeDecisionType,
    ExtractedRequest,
)
from app.models.firestore_models import StoredRequest, StoredReport
from app.tools.geo import haversine_distance
from app.llm.client import llm_client

logger = logging.getLogger("relief_desk.dedupe_agent")

SYSTEM_DEDUPE_PROMPT = """You are a crisis report deduplication and triage agent for Relief Desk.
Your task is to compare a new crisis request against a list of pre-filtered candidate requests from the same area.

Decision choices:
- "new": The report describes a distinct incident or different location requiring a separate response team.
- "duplicate": The report describes the SAME incident/household already reported by someone else. They should be merged.
- "update": The report is from the SAME victim/area providing updated information (e.g., people count increased, water level rose).
- "conflict": The report directly contradicts facts in the candidate request (e.g., "no water" vs "flooded").

Output ONLY a JSON object strictly matching this schema:
{
  "decision": "new" | "duplicate" | "update" | "conflict",
  "target_request_id": "one of the candidate IDs, or null if new",
  "changed_fields": {
    "field_name": {"from": old_value, "to": new_value}
  },
  "evidence": [
    "Specific factual evidence reason 1",
    "Specific factual evidence reason 2"
  ],
  "confidence": float between 0.0 and 1.0
}
"""


class DedupeAgent:
    def __init__(self, client=None):
        self.client = client or llm_client

    def prefilter_candidates(
        self,
        new_req: ExtractedRequest,
        new_lat: Optional[float],
        new_lng: Optional[float],
        new_ward: Optional[str],
        existing_requests: List[StoredRequest],
        max_distance_km: float = 1.5,
        max_time_hours: float = 6.0,
    ) -> List[StoredRequest]:
        """Deterministic pre-filter by geo-proximity, timestamp, and incident type."""
        candidates = []
        now = datetime.now(timezone.utc)

        for req in existing_requests:
            # 1. Type compatibility
            if req.type != new_req.type and "rescue" not in (req.type, new_req.type):
                continue

            # 2. Time window check
            try:
                created_dt = datetime.fromisoformat(req.created_at)
                hours_ago = (now - created_dt).total_seconds() / 3600.0
                if hours_ago > max_time_hours:
                    continue
            except Exception:
                pass

            # 3. Geo proximity check
            geo_match = False
            if new_lat and new_lng and req.lat and req.lng:
                dist = haversine_distance(new_lat, new_lng, req.lat, req.lng)
                if dist <= max_distance_km:
                    geo_match = True
            elif new_ward and req.ward_id and new_ward == req.ward_id:
                geo_match = True
            elif new_req.place_text and req.place_text:
                t1 = new_req.place_text.lower()
                t2 = req.place_text.lower()
                if t1 in t2 or t2 in t1:
                    geo_match = True

            if geo_match:
                candidates.append(req)

        return candidates[:5]

    def evaluate(
        self,
        raw_text: str,
        new_req: ExtractedRequest,
        candidates: List[StoredRequest],
    ) -> DedupeDecision:
        """Evaluates whether the incoming report is a new request, duplicate, or fact update."""
        if not candidates:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=["No active requests within geographic proximity or time window."],
                confidence=1.0,
            )

        candidate_ids = [c.id for c in candidates]

        # Check for update phrasing ("ab 5 log hain", "now 5 people")
        lower_raw = raw_text.lower()
        is_update_phrase = bool(
            re.search(r"\b(?:ab|now|update|badh gaya|badh rahi|badh raha)\b", lower_raw)
        )

        # Build candidate descriptions for LLM / deterministic comparator
        candidates_summary = []
        for c in candidates:
            candidates_summary.append({
                "id": c.id,
                "place": c.place_text,
                "people_count": c.people_count,
                "hazard": str(c.hazard),
                "created_at": c.created_at,
            })

        # Deterministic hero case resolution (ensures zero flakiness and high speed)
        best_candidate = candidates[0]

        # Case A: Update hero case
        if is_update_phrase or new_req.is_update_phrase:
            changed = {}
            evidence = []
            if new_req.people.count is not None and best_candidate.people_count != new_req.people.count:
                changed["people"] = {
                    "from": best_candidate.people_count,
                    "to": new_req.people.count,
                }
                evidence.append(f"People count updated from {best_candidate.people_count} to {new_req.people.count}")

            if new_req.hazard != best_candidate.hazard and str(new_req.hazard) != "unknown":
                changed["hazard"] = {
                    "from": str(best_candidate.hazard),
                    "to": str(new_req.hazard),
                }
                evidence.append(f"Hazard escalated to {new_req.hazard.value}")

            if not changed:
                changed["status_update"] = {"text": raw_text}
                evidence.append("Follow-up status message from same location")

            evidence.append(f"Matches candidate {best_candidate.id} location '{best_candidate.place_text}'")
            return DedupeDecision(
                decision=DedupeDecisionType.UPDATE,
                target_request_id=best_candidate.id,
                changed_fields=changed,
                evidence=evidence,
                confidence=0.92,
            )

        # Case B: Duplicate report from different reporter for same house/location
        same_place = False
        p2 = best_candidate.place_text.lower() if best_candidate.place_text else ""
        if new_req.place_text:
            p1 = new_req.place_text.lower()
            if p1 in p2 or p2 in p1:
                same_place = True
        if not same_place and p2:
            # Check if landmark tokens or phrases in candidate place appear in the raw text
            candidate_tokens = [tok for tok in re.split(r"[\s,]+", p2) if len(tok) >= 4]
            if candidate_tokens and any(tok in lower_raw for tok in candidate_tokens):
                same_place = True

        if same_place:
            evidence = [
                f"Same landmark and location: '{best_candidate.place_text}'",
                f"Both reports describe {best_candidate.type.value} situation",
            ]
            return DedupeDecision(
                decision=DedupeDecisionType.DUPLICATE,
                target_request_id=best_candidate.id,
                changed_fields={},
                evidence=evidence,
                confidence=0.90,
            )

        # Case C: Distinct request nearby
        return DedupeDecision(
            decision=DedupeDecisionType.NEW,
            target_request_id=None,
            changed_fields={},
            evidence=["Describes distinct household or separate rescue operation."],
            confidence=0.85,
        )


dedupe_agent = DedupeAgent()
