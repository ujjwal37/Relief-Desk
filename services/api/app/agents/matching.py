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
    ResourceStatus,
)
from app.models.schemas import IncidentType
from app.tools.geo import haversine_distance
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
    simulated: bool = False
    eta_minutes: Optional[int] = None
    no_nearby: bool = False
    wait_minutes: Optional[int] = None
    wait_team_name: Optional[str] = None
    soon_free: bool = False


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

        from app.tracking.availability import candidate_kind

        scored_candidates = []
        people_needed = request.people_count if request.people_count else 1

        for res in resources:
            kind = candidate_kind(res)
            if kind is None:
                continue
            breakdown = scoring_engine.compute_match_score(
                request, res, fallback_ok=False, soon_free=(kind == "soon_free")
            )
            if breakdown is None:
                continue
            scored_candidates.append((res, breakdown, False, kind))

        using_fallback = False
        if not scored_candidates:
            using_fallback = True
            for res in resources:
                breakdown = scoring_engine.compute_match_score(request, res, fallback_ok=True)
                if breakdown is None:
                    continue
                scored_candidates.append((res, breakdown, True, "fallback"))

        # Distance score is 0 past 10 km, so a far team with more seats can outrank a nearer one.
        # Keep teams near the closest suitable team. If every team is far, keep the closest and show its real ETA.
        scored_candidates = _keep_nearer(scored_candidates)

        # Score already includes live distance, seats, and type fit. Free teams rank above a soon-free team.
        scored_candidates.sort(
            key=lambda item: item[1].total_score - (8 if item[3] == "soon_free" else 0),
            reverse=True,
        )
        top_candidates = scored_candidates[:top_n]
        fallback_label = _fallback_label(request.type) if using_fallback else None
        wait_minutes, wait_team_name = (None, None)
        if using_fallback:
            wait_minutes, wait_team_name = _nearest_finish(request, resources)

        proposals: List[MatchProposal] = []
        for res, breakdown, is_fallback, kind in top_candidates:
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
                    simulated=bool(getattr(res, "simulated", False)),
                    eta_minutes=eta_for_distance(breakdown.distance_km),
                    no_nearby=breakdown.distance_km > NEARBY_KM,
                    wait_minutes=wait_minutes if is_fallback else None,
                    wait_team_name=wait_team_name if is_fallback else None,
                    soon_free=(kind == "soon_free"),
                )
            )

        logger.info(
            "MatchingAgent: Generated %d match proposals for request %s",
            len(proposals),
            request.id,
        )
        return proposals


# Quote a minute ETA only inside this radius. Farther than this, say there is no nearby team.
NEARBY_KM = 30.0
# A team inside this radius is close enough to prefer over a farther cluster.
PRACTICAL_KM = 40.0


def eta_for_distance(distance_km: float) -> Optional[int]:
    """Straight-line minutes at 20 km/h. None when the team is too far to quote."""
    if distance_km > NEARBY_KM:
        return None
    return max(1, round((distance_km / 20.0) * 60))


# How much farther than the nearest team we still offer as an alternative.
NEAR_BAND_KM = 15.0


def _keep_nearer(scored: list) -> list:
    if len(scored) <= 1:
        return scored
    nearest = min(item[1].distance_km for item in scored)
    if nearest <= PRACTICAL_KM:
        limit = min(PRACTICAL_KM, nearest + NEAR_BAND_KM)
    else:
        # Nothing is close. Keep the nearest cluster so one isolated team is not the only offer.
        limit = nearest * 1.15
    kept = [item for item in scored if item[1].distance_km <= limit + 0.05]
    return kept or scored


_PRIMARY = {
    IncidentType.RESCUE: [ResourceKind.BOAT],
    IncidentType.MEDICAL: [ResourceKind.MEDICAL],
    IncidentType.FOOD: [ResourceKind.FOOD],
    IncidentType.SHELTER: [ResourceKind.SHELTER],
    IncidentType.ANIMAL_ATTACK: [ResourceKind.MEDICAL],
}


def _finish_minutes(res: StoredResource) -> int:
    """Minutes until this team can take another case. Straight-line, 20 km/h, plus time on scene."""
    if res.status == ResourceStatus.ON_SCENE:
        return 20
    if res.status == ResourceStatus.RETURNING:
        return 15
    travel = 15
    if res.sim_target_lat is not None and res.sim_target_lng is not None:
        dist = haversine_distance(res.lat, res.lng, res.sim_target_lat, res.sim_target_lng)
        travel = max(1, round((dist / 20.0) * 60))
    if res.status in (ResourceStatus.EN_ROUTE, ResourceStatus.DISPATCHED):
        return travel + 20
    return travel + 20


def _nearest_finish(request: StoredRequest, resources: List[StoredResource]):
    kinds = _PRIMARY.get(request.type, [])
    busy = [
        res for res in resources
        if res.kind in kinds and res.status != ResourceStatus.AVAILABLE
    ]
    if not busy:
        return None, None

    def distance(res: StoredResource) -> float:
        if request.lat is None or request.lng is None:
            return 0.0
        return haversine_distance(request.lat, request.lng, res.lat, res.lng)

    nearest = min(busy, key=distance)
    if distance(nearest) > NEARBY_KM:
        return None, None
    return _finish_minutes(nearest), nearest.name


def _fallback_label(incident_type) -> str:
    from app.models.schemas import IncidentType
    return {
        IncidentType.RESCUE: "coord.noBoatFree",
        IncidentType.MEDICAL: "coord.noMedicalFree",
        IncidentType.FOOD: "coord.noFoodFree",
        IncidentType.SHELTER: "coord.noShelterFree",
    }.get(incident_type, "coord.noTeamFree")


matching_agent = MatchingAgent()
