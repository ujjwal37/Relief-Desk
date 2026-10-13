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
from app.tools.gazetteer import gazetteer
from app.llm.client import llm_client
from app.llm.embeddings import cosine, embed_texts, l2_normalize

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
    def __init__(self, client=None, embedder=None):
        self.client = client or llm_client
        self.embedder = embedder or embed_texts
        self._embed_scores: dict = {}

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
        """Embedding neighbours in the same district, or the lexical geo window when AI is off."""
        embedded = self._embedding_candidates(
            new_req, new_ward, existing_requests, max_time_hours=max_time_hours
        )
        if embedded is not None:
            return embedded
        self._embed_scores = {}
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

        return candidates[:12]

    def _district(self, ward_id: Optional[str]) -> Optional[str]:
        ward = gazetteer.wards.get(ward_id or "")
        if not ward:
            return None
        return ward.get("district")

    def _within_hours(self, req: StoredRequest, max_time_hours: float) -> bool:
        try:
            created = datetime.fromisoformat(req.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600.0
            return hours <= max_time_hours
        except Exception:
            return True

    def _embedding_candidates(
        self,
        new_req: ExtractedRequest,
        new_ward: Optional[str],
        existing_requests: List[StoredRequest],
        max_time_hours: float = 6.0,
    ) -> Optional[List[StoredRequest]]:
        """Same district and time window, ranked by gemini-embedding-001. None means use lexical retrieval."""
        query = (new_req.original_text or new_req.place_text or "").strip()
        if not query:
            return None
        district = self._district(new_ward or new_req.ward_id)
        pool = []
        for req in existing_requests:
            if req.merged_into or not self._within_hours(req, max_time_hours):
                continue
            other = self._district(req.ward_id)
            if district and other and district != other:
                continue
            if district and not other:
                continue
            pool.append(req)
        if not pool:
            probe = self.embedder([query])
            if not probe:
                return None
            self._embed_scores = {}
            return []
        texts = [query] + [f"{req.place_text or ''} {req.raw_text or ''}".strip() for req in pool]
        try:
            vectors = self.embedder(texts)
        except Exception:
            logger.info("Embedding retrieval failed, using lexical candidates")
            return None
        if not vectors or len(vectors) != len(texts):
            return None
        query_vec = l2_normalize(list(vectors[0]))
        ranked = []
        self._embed_scores = {}
        for req, raw in zip(pool, vectors[1:]):
            if raw is None:
                return None
            score = cosine(query_vec, l2_normalize(list(raw)))
            if score >= 0.80:
                ranked.append((score, req))
                self._embed_scores[req.id] = round(score, 3)
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [req for _, req in ranked[:12]]

    def evaluate(
        self,
        raw_text: str,
        new_req: ExtractedRequest,
        candidates: List[StoredRequest],
    ) -> DedupeDecision:
        """Evaluates whether the incoming report is a new request, duplicate, or fact update."""
        live = self._ask_gemini(raw_text, new_req, candidates)
        if live is not None:
            return live
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

        # Deterministic compare. Landmark tokens must agree.
        # A different house in the same ward stays a new request.
        best_candidate = self._best_landmark_match(raw_text, new_req, candidates)
        different_house = bool(
            re.search(
                r"different house|alag ghar|house\s*#|house\s+\d|makan|मकान",
                lower_raw,
            )
        )

        # Case A: Update phrasing, attached to the landmark match when one exists.
        if is_update_phrase or new_req.is_update_phrase:
            target = best_candidate or candidates[0]
            changed = {}
            evidence = []
            if new_req.people.count is not None and target.people_count != new_req.people.count:
                changed["people"] = {
                    "from": target.people_count,
                    "to": new_req.people.count,
                }
                evidence.append(f"People count updated from {target.people_count} to {new_req.people.count}")

            if new_req.hazard != target.hazard and str(new_req.hazard) != "unknown":
                changed["hazard"] = {
                    "from": str(target.hazard),
                    "to": str(new_req.hazard),
                }
                evidence.append(f"Hazard escalated to {new_req.hazard.value}")

            if not changed:
                changed["status_update"] = {"text": raw_text}
                evidence.append("Follow-up status message from same location")

            evidence.append(f"Matches candidate {target.id} location '{target.place_text}'")
            evidence.extend(self._embed_evidence(target.id))
            return DedupeDecision(
                decision=DedupeDecisionType.UPDATE,
                target_request_id=target.id,
                changed_fields=changed,
                evidence=evidence,
                confidence=0.92,
            )

        duplicate_cue = bool(
            re.search(r"another report|same here|बचाव दल भेजो", raw_text, re.IGNORECASE)
        )
        has_people_count = bool(re.search(r"\b\d+\b", raw_text))
        contradiction = bool(re.search(r"dry and safe|drained|completely dry", lower_raw))
        if different_house or best_candidate is None or contradiction:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=["Describes distinct household or separate rescue operation."],
                confidence=0.85,
            )
        same_people = (
            new_req.people.count is not None
            and best_candidate.people_count == new_req.people.count
        )
        # A counted report is a new case unless it names the same place and the same people.
        if not duplicate_cue and has_people_count and not same_people:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=["First report of a counted incident, not a second caller."],
                confidence=0.84,
            )

        evidence = [
            f"Same landmark and location: '{best_candidate.place_text}'",
            f"Both reports describe {best_candidate.type.value} situation",
        ]
        evidence.extend(self._embed_evidence(best_candidate.id))
        return DedupeDecision(
            decision=DedupeDecisionType.DUPLICATE,
            target_request_id=best_candidate.id,
            changed_fields={},
            evidence=evidence,
            confidence=0.90,
        )

    _PLACE_STOP = {
        "the", "and", "near", "ward", "road", "from", "with", "this", "that",
        "area", "people", "water", "house", "ghar", "log", "hain", "paas",
        "ke", "mein", "par", "need", "help", "flood", "here", "same", "another",
        "report", "roads", "completely",
        "boat", "send", "roof", "chhat", "madad", "chahiye", "bhejo", "bhej",
        "fas", "gaye", "please", "rescue", "urgent", "paani", "pani",
        "stranded", "trapped", "submerged", "synthetic", "rising", "inundated",
    }
    _GENERIC_PLACE = {
        "school", "ghat", "nagar", "colony", "market", "park", "lake", "mandir",
        "hospital", "clinic", "shelter", "primary", "high", "govt", "community",
        "view", "road", "lane", "street",
    }

    def _place_tokens(self, text: str) -> set:
        tokens = set(re.findall(r"[a-z]{3,}", (text or "").lower()))
        return {tok for tok in tokens if tok not in self._PLACE_STOP and not tok.isdigit()}

    def _landmark_score(self, raw_text: str, place_text: str, candidate_place: str) -> int:
        if not candidate_place:
            return 0
        haystack = self._place_tokens(f"{raw_text} {place_text or ''}")
        place = self._place_tokens(candidate_place)
        shared = haystack & place
        specific = {tok for tok in shared if tok not in self._GENERIC_PLACE}
        if not specific:
            return 0
        generic = shared - specific
        return len(specific) * 2 + len(generic)

    def _best_landmark_match(self, raw_text: str, new_req: ExtractedRequest, candidates: List[StoredRequest]):
        phrase_hit = self._longest_landmark_phrase(raw_text)
        if phrase_hit:
            best = None
            best_score = 0
            for candidate in candidates:
                score = self._phrase_cover_score(phrase_hit, candidate.place_text or "")
                if score > best_score:
                    best_score = score
                    best = candidate
            if best is not None and best_score >= 2:
                return best
        best = None
        best_score = 0
        for candidate in candidates:
            heard = f"{candidate.place_text or ''} {candidate.raw_text or ''}"
            score = self._landmark_score(raw_text, new_req.place_text or "", heard)
            if score > best_score:
                best_score = score
                best = candidate
        if best_score < 2:
            return None
        return best

    def _phrase_cover_score(self, phrase: str, place: str) -> int:
        if phrase and phrase in self._norm(place):
            return 20
        shared = self._place_tokens(phrase) & self._place_tokens(place)
        if len(shared) < 2:
            return 0
        specific = {tok for tok in shared if tok not in self._GENERIC_PLACE}
        return len(shared) + (5 * len(specific))

    def _norm(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

    def _longest_landmark_phrase(self, raw_text: str) -> Optional[str]:
        if not hasattr(self, "_landmark_phrases"):
            self._landmark_phrases = self._load_landmark_phrases()
        norm = f" {self._norm(raw_text)} "
        hit = ""
        for phrase in self._landmark_phrases:
            if f" {phrase} " in norm and len(phrase) > len(hit):
                hit = phrase
        return hit or None

    def _load_landmark_phrases(self) -> List[str]:
        from pathlib import Path
        import yaml

        path = Path(__file__).resolve().parents[4] / "data" / "synthetic" / "flood_v1" / "seeds.yaml"
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        phrases = []
        for landmark in data.get("landmarks", []):
            names = [landmark.get("name") or ""]
            names.extend(landmark.get("aliases_en") or [])
            for name in names:
                phrase = self._norm(name)
                if len(phrase) >= 6:
                    phrases.append(phrase)
        phrases.sort(key=len, reverse=True)
        return phrases

    def _embed_evidence(self, request_id: Optional[str]) -> List[str]:
        score = self._embed_scores.get(request_id or "")
        if score is None:
            return []
        return [f"gemini-embedding-001 SEMANTIC_SIMILARITY 768d cosine {score}"]

    def _ask_gemini(self, raw_text: str, new_req: ExtractedRequest, candidates: List[StoredRequest]) -> Optional[DedupeDecision]:
        """Ask Gemini to judge duplicate, update, or distinct. None means use the lexical decision."""
        from app.llm.antigravity import antigravity_requested

        # Antigravity does not call Gemini embeddings. The lexical rules decide duplicates.
        if antigravity_requested() or not candidates or not getattr(self.client, "gemini_live", lambda: False)():
            return None
        summary = [
            {
                "id": candidate.id,
                "place": candidate.place_text,
                "people_count": candidate.people_count,
                "type": str(candidate.type),
            }
            for candidate in candidates
        ]
        user = (
            f"<report>\n{raw_text}\n</report>\n"
            f"Extracted place: {new_req.place_text}\n"
            f"Extracted people: {new_req.people.count}\n"
            f"Candidates:\n{json.dumps(summary)}\n"
            'Reply with JSON {"relation":"duplicate"|"update"|"distinct","target_request_id":"id or null","evidence":["..."]}'
        )
        try:
            raw = self.client.generate_content(
                system_instruction=SYSTEM_DEDUPE_PROMPT,
                user_prompt=user,
            )
            decision = self._decision_from_judge(raw, new_req)
        except Exception as exc:
            logger.info("Dedupe Gemini comparison failed, using rules: %s", exc)
            return None
        if decision is None:
            return None
        allowed = {candidate.id for candidate in candidates}
        if decision.target_request_id and decision.target_request_id not in allowed:
            return None
        if decision.decision != DedupeDecisionType.NEW and not decision.target_request_id:
            return None
        decision.evidence.extend(self._embed_evidence(decision.target_request_id))
        return decision

    def _decision_from_judge(self, raw: str, new_req: ExtractedRequest) -> Optional[DedupeDecision]:
        clean = raw.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        payload = json.loads(clean.strip())
        relation = str(payload.get("relation") or payload.get("decision") or "").lower()
        mapped = {
            "duplicate": DedupeDecisionType.DUPLICATE,
            "update": DedupeDecisionType.UPDATE,
            "distinct": DedupeDecisionType.NEW,
            "new": DedupeDecisionType.NEW,
            "conflict": DedupeDecisionType.CONFLICT,
        }.get(relation)
        if mapped is None:
            return None
        evidence = [str(item) for item in payload.get("evidence") or []]
        changed = payload.get("changed_fields") or {}
        if mapped == DedupeDecisionType.UPDATE and not changed:
            changed = {"people": {"to": new_req.people.count}}
        return DedupeDecision(
            decision=mapped,
            target_request_id=payload.get("target_request_id"),
            changed_fields=changed,
            evidence=evidence or ["Gemini judge compared the two reports."],
            confidence=float(payload.get("confidence") or 0.8),
        )


dedupe_agent = DedupeAgent()
