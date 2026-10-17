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

# Same place, same type, and this score: merge. Under it, the coordinator reviews.
AUTO_MERGE_CONFIDENCE = 0.80
REVIEW_CONFIDENCE = 0.50
RETRIEVE_COSINE = 0.70
# An update phrase with no landmark match only attaches to a case this close.
UPDATE_NEAR_KM = 0.3
# Measured similarity under this does not auto-merge, unless it is the same gazetteer landmark.
MIN_MERGE_SIMILARITY = 0.60
# Different landmarks merge only when the reports are nearly the same text.
VERY_HIGH_SIMILARITY = 0.85

# Devanagari to rough Latin, so "नेदुमुडी" and "Nedumudi" share character trigrams without embeddings.
_DEVA = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e",
    "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri", "ं": "n", "ँ": "n", "ः": "h", "़": "", "्": "",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}


def transliterate(text: str) -> str:
    out = "".join(_DEVA.get(ch, ch) for ch in (text or ""))
    out = out.lower().replace("w", "v").replace("ee", "i").replace("oo", "u").replace("aa", "a")
    return re.sub(r"[^a-z0-9 ]+", " ", out)


def trigram_similarity(left: str, right: str) -> float:
    """Character-trigram Jaccard on transliterated text. Works for Hindi, Hinglish and English."""
    def grams(text: str) -> set:
        words = [w for w in transliterate(text).split() if len(w) >= 3]
        return {w[i:i + 3] for w in words for i in range(len(w) - 2)}
    a, b = grams(left), grams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def confidence_phrase(similarity: Optional[float], distance_km: Optional[float], minutes: Optional[float]) -> str:
    """The match evidence in plain words: place, time and wording. No raw scores."""
    parts = []
    if distance_km is None:
        parts.append("Place not stated")
    elif float(distance_km) <= 0.3:
        parts.append(f"Same landmark ({float(distance_km):.2f} km)")
    else:
        parts.append(f"{float(distance_km):.1f} km apart")
    if minutes is not None:
        parts.append(f"{int(round(float(minutes)))} min apart")
    if similarity is not None and float(similarity) >= 0.6:
        parts.append("very similar wording")
    elif similarity is not None and float(similarity) >= 0.3:
        parts.append("similar wording")
    return "Match evidence: " + " + ".join(parts)


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
            kinds = (self._type_name(req.type), self._type_name(new_req.type))
            if kinds[0] != kinds[1] and "rescue" not in kinds:
                continue

            # 2. Time window check (naive timestamps are UTC)
            if not self._within_hours(req, max_time_hours):
                continue

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

            if req.merged_into:
                continue

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
            # Retrieval only. Hindi vs English of the same place often scores 0.7-0.8; the merge bar is separate.
            if score >= RETRIEVE_COSINE:
                ranked.append((score, req))
                self._embed_scores[req.id] = round(score, 3)
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [req for _, req in ranked[:12]]

    def evaluate(
        self,
        raw_text: str,
        new_req: ExtractedRequest,
        candidates: List[StoredRequest],
        new_lat: Optional[float] = None,
        new_lng: Optional[float] = None,
        judge: bool = True,
    ) -> DedupeDecision:
        """Evaluates whether the incoming report is a new request, duplicate, or fact update.

        judge=False is the report path: embeddings and rules decide inside the merge budget,
        without waiting for a model slot.
        """
        live = self._ask_gemini(raw_text, new_req, candidates) if judge else None
        if live is not None and live.decision != DedupeDecisionType.DUPLICATE:
            return live
        if not candidates:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=["No active requests within geographic proximity or time window."],
                confidence=1.0,
            )

        # Check for update phrasing ("ab 5 log hain", "now 5 people")
        lower_raw = raw_text.lower()
        is_update_phrase = bool(
            re.search(r"\b(?:ab|now|update|badh gaya|badh rahi|badh raha)\b", lower_raw)
        )

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
        # "ab 5 log hain" still updates the nearest pin. A different landmark does not.
        update_target = best_candidate or self._nearest_within(candidates, new_lat, new_lng, UPDATE_NEAR_KM)
        if update_target is not None and self._landmarks_differ(raw_text, new_req, update_target):
            update_target = None
        if (is_update_phrase or new_req.is_update_phrase) and update_target is not None:
            # "now" alone is common ("need food now"); it only updates a case with the same landmark or pin.
            target = update_target
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

        contradiction = bool(re.search(r"dry and safe|drained|completely dry", lower_raw))
        if different_house or contradiction:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=["Describes distinct household or separate rescue operation."],
                confidence=0.85,
            )

        pair = self._best_pair(raw_text, new_req, candidates, new_lat, new_lng)
        if live is not None:
            decision = self._gate_model_duplicate(live, pair)
        else:
            decision = self._decision_from_score(pair)
        return self._count_guard(decision, pair, new_req)

    def _count_guard(self, decision: DedupeDecision, pair, new_req: ExtractedRequest) -> DedupeDecision:
        """Conflicting head counts never auto-merge. The coordinator reviews the pair."""
        if pair is None:
            return decision
        facts, cand = pair
        if not facts.get("counts_conflict"):
            return decision
        if decision.decision != DedupeDecisionType.DUPLICATE and not decision.review:
            return decision
        note = facts.get("counts_note") or "Counts differ"
        if decision.decision == DedupeDecisionType.DUPLICATE:
            decision = self._review_decision(cand, facts)
        if note not in decision.evidence:
            decision.evidence.append(note)
        return decision

    def _nearest_within(self, candidates, lat, lng, km):
        if lat is None or lng is None:
            return None
        best, best_d = None, None
        for cand in candidates:
            if cand.lat is None or cand.lng is None or cand.merged_into:
                continue
            d = haversine_distance(float(lat), float(lng), float(cand.lat), float(cand.lng))
            if d <= km and (best_d is None or d < best_d):
                best, best_d = cand, d
        return best

    def _type_name(self, value) -> str:
        return str(getattr(value, "value", value))

    def _minutes_since(self, req: StoredRequest) -> Optional[float]:
        try:
            created = datetime.fromisoformat(req.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 60.0)
        except Exception:
            return None

    def _same_place_phrase(self, incoming: str, place: str) -> bool:
        """'Church Road' is the same street even though both words are ordinary."""
        phrase = self._norm(place)
        if len(phrase) < 8:
            return False
        return phrase in self._norm(incoming)

    def _specific_places(self, text: str) -> set:
        return {tok for tok in self._place_tokens(text) if tok not in self._GENERIC_PLACE}

    def _sim_tokens(self, text: str) -> set:
        stop = {"the", "and", "near", "from", "with", "this", "that", "please", "need", "help", "send", "for", "are", "was"}
        stop = {transliterate(w).strip() for w in stop}
        return {tok for tok in re.findall(r"[a-z]{3,}", transliterate(text)) if tok not in stop}

    def _jaccard(self, left: set, right: set) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _pair_facts(
        self,
        raw_text: str,
        new_req: ExtractedRequest,
        cand: StoredRequest,
        new_lat: Optional[float],
        new_lng: Optional[float],
    ) -> dict:
        heard = f"{cand.place_text or ''} {cand.raw_text or ''}"
        incoming = f"{raw_text} {new_req.place_text or ''}"
        overlap = max(
            self._jaccard(self._sim_tokens(incoming), self._sim_tokens(heard)),
            # Spelling and script vary (Hindi vs Latin), so character trigrams back up the word overlap.
            round(trigram_similarity(incoming, heard) * 1.2, 3),
        )
        overlap = min(1.0, overlap)
        shared = self._specific_places(incoming) & self._specific_places(heard)
        distinctive = {tok for tok in shared if len(tok) >= 6}
        phrase = self._same_place_phrase(incoming, cand.place_text or "")
        incoming_ids = self._landmark_ids(incoming)
        heard_ids = self._landmark_ids(heard)
        same_landmark = bool(incoming_ids and heard_ids and (incoming_ids & heard_ids))
        places_differ = bool(incoming_ids and heard_ids and not (incoming_ids & heard_ids))
        place_missing = not self._real_place(raw_text, new_req.place_text or "") or not self._real_place(
            cand.raw_text or "", cand.place_text or ""
        )
        incoming_places = self._specific_places(incoming)
        heard_places = self._specific_places(heard)
        conflicting = bool(
            incoming_places and heard_places and not shared and not phrase and not same_landmark
        )
        if places_differ and overlap < VERY_HIGH_SIMILARITY:
            conflicting = True
        # Champakulam and Kainakary, or Pulinkunnu and Kainakary, are different places.
        ward_new = gazetteer.resolve_ward(new_req.place_text, raw_text)
        ward_old = gazetteer.resolve_ward(cand.place_text, cand.raw_text or "")
        if ward_new and ward_old and ward_new != ward_old and not same_landmark:
            places_differ = True
            conflicting = True
        confirmed = bool(
            not place_missing
            and not (places_differ and overlap < VERY_HIGH_SIMILARITY)
            and (same_landmark or phrase or bool(distinctive) or overlap >= VERY_HIGH_SIMILARITY)
        )
        distance = None
        if new_lat is not None and new_lng is not None and cand.lat is not None and cand.lng is not None:
            distance = haversine_distance(float(new_lat), float(new_lng), float(cand.lat), float(cand.lng))
            if distance > 5 or (distance > 1.5 and not same_landmark):
                confirmed = False
                conflicting = True
        minutes = self._minutes_since(cand)
        # Same gazetteer landmark, or a shared distinctive token, is strong evidence across wording.
        strong = bool(confirmed and (same_landmark or distinctive or phrase))
        sim_for_score = max(overlap, 0.88) if strong else overlap
        if distance is None:
            dist_score = 0.95 if confirmed else 0.35
        else:
            dist_score = max(0.0, 1.0 - (distance / 1.5))
        time_score = 0.95 if minutes is None else max(0.0, 1.0 - (minutes / 120.0))
        confidence = round(min(0.99, 0.5 * sim_for_score + 0.3 * dist_score + 0.2 * time_score), 2)
        new_count, old_count = new_req.people.count, cand.people_count
        counts_conflict = bool(new_count and old_count and int(new_count) != int(old_count))
        counts_note = f"Counts differ: {old_count} vs {new_count}" if counts_conflict else None
        # Show the measured similarity, not a floor.
        shown = round(overlap, 2)
        return {
            "similarity": shown,
            "distance_km": None if distance is None else round(distance, 2),
            "minutes": None if minutes is None else round(minutes, 1),
            "confirmed": confirmed,
            "conflicting": conflicting,
            "confidence": confidence,
            "same_landmark": same_landmark,
            "places_differ": places_differ,
            "place_missing": place_missing,
            "distinctive": bool(distinctive),
            "counts_conflict": counts_conflict,
            "counts_note": counts_note,
        }

    def _best_pair(
        self,
        raw_text: str,
        new_req: ExtractedRequest,
        candidates: List[StoredRequest],
        new_lat: Optional[float],
        new_lng: Optional[float],
    ):
        best = None
        wanted = self._type_name(new_req.type)
        for cand in candidates:
            if cand.merged_into or self._type_name(cand.type) != wanted:
                continue
            facts = self._pair_facts(raw_text, new_req, cand, new_lat, new_lng)
            if facts["conflicting"]:
                continue
            if best is None or facts["confidence"] > best[0]["confidence"] or (
                facts["confidence"] == best[0]["confidence"] and cand.id < best[1].id
            ):
                best = (facts, cand)
        return best

    def _should_duplicate(self, facts: dict) -> bool:
        """Auto-merge only for the same place with compatible head counts."""
        if not facts or facts.get("place_missing") or facts.get("counts_conflict"):
            return False
        if facts.get("places_differ") and facts.get("similarity", 0) < VERY_HIGH_SIMILARITY:
            return False
        if not facts.get("confirmed") or facts.get("confidence", 0) < AUTO_MERGE_CONFIDENCE:
            return False
        if facts.get("same_landmark") or facts.get("distinctive"):
            return True
        return facts.get("similarity", 0) >= MIN_MERGE_SIMILARITY

    def _landmark_ids(self, text: str) -> set:
        if not (text or "").strip():
            return set()
        return gazetteer.landmark_ids_in(text)

    def _content_tokens(self, text: str) -> list:
        # Keep place words such as "road" even when they are also ordinary stop words.
        return [
            tok for tok in re.findall(r"[a-z0-9]{3,}", transliterate(text or ""))
            if not tok.isdigit() and (tok in self._GENERIC_PLACE or tok not in self._PLACE_STOP)
        ]

    def _named_place_tokens(self, text: str) -> set:
        """A long name sitting next to a place word: 'Gandhi school', 'Oakbend ghat'."""
        tokens = re.findall(r"[a-z0-9]{3,}", transliterate(text or ""))
        named = set()
        for index, token in enumerate(tokens):
            if len(token) < 6 or token.isdigit() or token in self._PLACE_STOP or token in self._GENERIC_PLACE:
                continue
            window = tokens[max(0, index - 2): index + 3]
            if any(word in self._GENERIC_PLACE for word in window):
                named.add(token)
        return named

    def _place_phrases(self, text: str) -> set:
        """'Church Road' is a place even though each word is ordinary."""
        tokens = self._content_tokens(text)
        phrases = set()
        for index in range(len(tokens) - 1):
            pair = tokens[index:index + 2]
            if not any(tok in self._GENERIC_PLACE for tok in pair):
                continue
            phrase = " ".join(pair)
            if len(phrase) >= 8:
                phrases.add(phrase)
        return phrases

    def _coded_place_tokens(self, text: str) -> set:
        """A made-up landmark token such as Mithralaneab12, not a bare number."""
        found = set()
        for tok in re.findall(r"[a-z0-9]{6,}", transliterate(text or "")):
            if tok in self._PLACE_STOP or tok in self._GENERIC_PLACE or tok.isdigit():
                continue
            if any(ch.isdigit() for ch in tok):
                found.add(tok)
        return found

    def _real_place(self, text: str, place_text: str) -> bool:
        """A gazetteer landmark, a street phrase, or a name the reporter actually gave."""
        blob = f"{place_text or ''} {text or ''}"
        if self._landmark_ids(blob):
            return True
        if any(len(tok) >= 6 for tok in self._specific_places(place_text or "")):
            return True
        if self._named_place_tokens(blob) or self._place_phrases(blob) or self._coded_place_tokens(blob):
            return True
        return False

    def _landmarks_differ(self, raw_text: str, new_req: ExtractedRequest, cand: StoredRequest) -> bool:
        new_ids = self._landmark_ids(f"{raw_text} {new_req.place_text or ''}")
        old_ids = self._landmark_ids(f"{cand.place_text or ''} {cand.raw_text or ''}")
        return bool(new_ids and old_ids and not (new_ids & old_ids))

    def _stamp(self, decision: DedupeDecision, facts: dict) -> DedupeDecision:
        decision.similarity = facts["similarity"]
        decision.distance_km = facts["distance_km"]
        decision.minutes_apart = facts["minutes"]
        decision.confidence = facts["confidence"]
        line = confidence_phrase(facts["similarity"], facts["distance_km"], facts["minutes"])
        if line not in decision.evidence:
            decision.evidence.append(line)
        return decision

    def _review_decision(self, cand: StoredRequest, facts: dict) -> DedupeDecision:
        line = confidence_phrase(facts["similarity"], facts["distance_km"], facts["minutes"])
        return DedupeDecision(
            decision=DedupeDecisionType.NEW,
            target_request_id=cand.id,
            changed_fields={},
            evidence=[line, "Below the merge threshold. Possible duplicate, review."],
            confidence=facts["confidence"],
            similarity=facts["similarity"],
            distance_km=facts["distance_km"],
            minutes_apart=facts["minutes"],
            review=True,
        )

    def _decision_from_score(self, pair) -> DedupeDecision:
        if pair is None:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=["Different place or type. Not merged."],
                confidence=0.86,
            )
        facts, cand = pair
        line = confidence_phrase(facts["similarity"], facts["distance_km"], facts["minutes"])
        if facts.get("place_missing"):
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=[line, "No place named. Not merged on place."],
                confidence=facts["confidence"],
                similarity=facts["similarity"],
                distance_km=facts["distance_km"],
                minutes_apart=facts["minutes"],
            )
        if self._should_duplicate(facts):
            evidence = [
                f"Same landmark and location: '{cand.place_text}'",
                f"Both reports describe {self._type_name(cand.type)} situation",
                line,
            ]
            evidence.extend(self._embed_evidence(cand.id))
            return DedupeDecision(
                decision=DedupeDecisionType.DUPLICATE,
                target_request_id=cand.id,
                changed_fields={},
                evidence=evidence,
                confidence=facts["confidence"],
                similarity=facts["similarity"],
                distance_km=facts["distance_km"],
                minutes_apart=facts["minutes"],
            )
        if facts.get("counts_conflict") and (facts.get("confirmed") or facts.get("same_landmark")):
            review = self._review_decision(cand, facts)
            note = facts.get("counts_note")
            if note and note not in review.evidence:
                review.evidence.append(note)
            return review
        if (
            not facts.get("place_missing")
            and facts["confidence"] >= REVIEW_CONFIDENCE
            and (facts["confirmed"] or facts["similarity"] >= MIN_MERGE_SIMILARITY)
        ):
            return self._review_decision(cand, facts)
        return DedupeDecision(
            decision=DedupeDecisionType.NEW,
            target_request_id=None,
            changed_fields={},
            evidence=[line, "Not the same incident."],
            confidence=facts["confidence"],
            similarity=facts["similarity"],
            distance_km=facts["distance_km"],
            minutes_apart=facts["minutes"],
        )

    def _gate_model_duplicate(self, live: DedupeDecision, pair) -> DedupeDecision:
        """A model duplicate still has to clear the same place, type, and confidence bar."""
        if pair is None:
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=list(live.evidence) + ["Different place or type. Not merged."],
                confidence=live.confidence,
            )
        facts, cand = pair
        if facts.get("place_missing"):
            return DedupeDecision(
                decision=DedupeDecisionType.NEW,
                target_request_id=None,
                changed_fields={},
                evidence=list(live.evidence) + ["No place named. Not merged on place."],
                confidence=facts["confidence"],
                similarity=facts["similarity"],
                distance_km=facts["distance_km"],
                minutes_apart=facts["minutes"],
            )
        if self._should_duplicate(facts):
            live.target_request_id = cand.id
            live.decision = DedupeDecisionType.DUPLICATE
            live.review = False
            return self._stamp(live, facts)
        if facts.get("counts_conflict") and (facts.get("confirmed") or facts.get("same_landmark")):
            review = self._review_decision(cand, facts)
            note = facts.get("counts_note")
            if note and note not in review.evidence:
                review.evidence.append(note)
            return review
        if facts["confidence"] >= REVIEW_CONFIDENCE and not facts.get("place_missing"):
            return self._review_decision(cand, facts)
        return DedupeDecision(
            decision=DedupeDecisionType.NEW,
            target_request_id=None,
            changed_fields={},
            evidence=list(live.evidence),
            confidence=facts["confidence"],
            similarity=facts["similarity"],
            distance_km=facts["distance_km"],
            minutes_apart=facts["minutes"],
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
        "view", "road", "lane", "street", "jetty", "ferry", "bridge", "temple",
        "church", "bazaar", "canal", "river", "bund", "gate",
    }

    def _place_tokens(self, text: str) -> set:
        tokens = set(re.findall(r"[a-z]{3,}", transliterate(text)))
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
        return re.sub(r"[^a-z0-9]+", " ", transliterate(text)).strip()

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
        from app.llm.embeddings import describe

        return [f"{describe()} {score}"]

    def _ask_gemini(self, raw_text: str, new_req: ExtractedRequest, candidates: List[StoredRequest]) -> Optional[DedupeDecision]:
        """Ask Gemini to judge duplicate, update, or distinct. None means use the lexical decision."""
        from app.llm import openai_compat as oc
        from app.llm.antigravity import antigravity_requested

        # Antigravity does not call Gemini embeddings. The lexical rules decide duplicates.
        if antigravity_requested() or not candidates:
            return None
        if oc.requested() and not oc.enabled():
            return None
        if not oc.requested() and not getattr(self.client, "gemini_live", lambda: False)():
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

    def _judge_name(self) -> str:
        from app.llm.providers import display_name

        usage = getattr(self.client, "last_ai", None)
        provider = getattr(usage, "provider", None)
        provider = provider if isinstance(provider, str) and provider else "gemini"
        return f"{display_name(provider)} judge" if provider != "fallback" else "Rules judge"

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
            evidence=evidence or [f"{self._judge_name()} compared the two reports."],
            confidence=float(payload.get("confidence") or 0.8),
        )


# Token sets go through the same normalisation as the text they are compared with.
DedupeAgent._PLACE_STOP = {transliterate(w).strip() for w in DedupeAgent._PLACE_STOP}
DedupeAgent._GENERIC_PLACE = {transliterate(w).strip() for w in DedupeAgent._GENERIC_PLACE}

dedupe_agent = DedupeAgent()
