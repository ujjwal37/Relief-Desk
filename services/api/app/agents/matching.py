import logging
import uuid
from typing import List, Optional
from pydantic import BaseModel
from app.models.firestore_models import (
    StoredRequest,
    StoredResource,
    StoredMatch,
    MatchState,
    MatchBreakdown,
    ResourceKind,
)
from app.tools.storage import storage_service
from app.tools.scoring import scoring_engine
from app.agents.explainer import explainer_agent

logger = logging.getLogger("relief_desk.matching_agent")


class MatchProposal(BaseModel):
    match_id: str
    request_id: str
    resource_id: str
    resource_name: str
    resource_kind: ResourceKind
    resource_ward: str
    capacity_total: int
    capacity_remaining: int
    score: float
    breakdown: MatchBreakdown
    explanation: Optional[str] = None
    explanation_hi: Optional[str] = None
    state: MatchState = MatchState.PROPOSED
    overcommit_warning: bool = False
    is_fallback: bool = False
    fallback_label: Optional[str] = None


class MatchingAgent:
    """
    Deterministic matching agent (orchestration only).
    Evaluates seeded candidate resources against the incoming request,
    computes score breakdown (distance, capacity, urgency, vulnerability),
    persists proposed matches, and returns ordered proposals.
    """

    def find_matches(
        self,
        request: StoredRequest,
        top_n: int = 5,
        save_to_storage: bool = True,
    ) -> List[MatchProposal]:
        resources = storage_service.list_resources(event_id=request.event_id)
        if not resources:
            storage_service.load_seed_resources()
            resources = storage_service.list_resources(event_id=request.event_id)

        scored_candidates = []
        people_needed = request.people_count if request.people_count else 1

        for res in resources:
            breakdown = scoring_engine.compute_match_score(request, res, fallback_ok=False)
            if breakdown is None:
                continue
            scored_candidates.append((res, breakdown, False))

        using_fallback = False
        if not scored_candidates:
            using_fallback = True
            for res in resources:
                breakdown = scoring_engine.compute_match_score(request, res, fallback_ok=True)
                if breakdown is None:
                    continue
                scored_candidates.append((res, breakdown, True))

        # Sort by total_score descending. Primary matches never mix with a fallback list.
        scored_candidates.sort(key=lambda item: item[1].total_score, reverse=True)
        top_candidates = scored_candidates[:top_n]
        fallback_label = _fallback_label(request.type) if using_fallback else None

        proposals: List[MatchProposal] = []
        for res, breakdown, is_fallback in top_candidates:
            # Check if there is an existing match in storage
            existing = [
                m
                for m in storage_service.list_matches_for_request(request.id)
                if m.resource_id == res.id
            ]

            is_overcommit = people_needed > res.capacity_remaining
            explanation = explainer_agent.explain(request, res, breakdown)

            if existing:
                match = existing[0]
                match.score = breakdown.total_score
                match.breakdown = breakdown
                match.overcommit = is_overcommit
                match.explanation = explanation.text_en
                match.explanation_hi = explanation.text_hi
                if save_to_storage:
                    storage_service.save_match(match, actor="matching_agent")
            else:
                match_id = f"match_{uuid.uuid4().hex[:10]}"
                match = StoredMatch(
                    id=match_id,
                    request_id=request.id,
                    resource_id=res.id,
                    score=breakdown.total_score,
                    breakdown=breakdown,
                    explanation=explanation.text_en,
                    explanation_hi=explanation.text_hi,
                    state=MatchState.PROPOSED,
                    overcommit=is_overcommit,
                )
                if save_to_storage:
                    storage_service.save_match(match, actor="matching_agent")

            proposals.append(
                MatchProposal(
                    match_id=match.id,
                    request_id=request.id,
                    resource_id=res.id,
                    resource_name=res.name,
                    resource_kind=res.kind,
                    resource_ward=res.ward_id,
                    capacity_total=res.capacity_total,
                    capacity_remaining=res.capacity_remaining,
                    score=breakdown.total_score,
                    breakdown=breakdown,
                    explanation=match.explanation,
                    explanation_hi=match.explanation_hi,
                    state=match.state,
                    overcommit_warning=is_overcommit,
                    is_fallback=is_fallback,
                    fallback_label=fallback_label if is_fallback else None,
                )
            )

        logger.info(
            "MatchingAgent: Generated %d match proposals for request %s",
            len(proposals),
            request.id,
        )
        return proposals


def _fallback_label(incident_type) -> str:
    from app.models.schemas import IncidentType
    return {
        IncidentType.RESCUE: "coord.noBoatFree",
        IncidentType.MEDICAL: "coord.noMedicalFree",
        IncidentType.FOOD: "coord.noFoodFree",
        IncidentType.SHELTER: "coord.noShelterFree",
    }.get(incident_type, "coord.noTeamFree")


matching_agent = MatchingAgent()
