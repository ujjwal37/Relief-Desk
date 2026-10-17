import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
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
    # water: a boat crosses flood water in a straight line; road: a land team drives.
    travel_mode: str = "road"
    no_nearby: bool = False
    wait_minutes: Optional[int] = None
    wait_team_name: Optional[str] = None
    # Honest boat-vs-road comparison from the same haversine distance. Never invents closures.
    route_note: Optional[str] = None
    # Set when this team is also the best team for a more urgent waiting case (warning only).
    takes_from: Optional[Dict[str, Any]] = None


def _explain_together(request: StoredRequest, candidates: list, use_model: bool = False) -> list:
    """Team explanations come from the template by default.

    Ranking runs on every case open and after every report, so a model call here would queue
    behind intake on a slow model. use_model=True asks the Explainer for each team.
    """
    if not use_model:
        return [explainer_agent.generate_template_fallback(request, res, breakdown) for res, breakdown, _ in candidates]
    if len(candidates) < 2:
        return [explainer_agent.explain(request, res, breakdown) for res, breakdown, _ in candidates]
    workers = min(4, len(candidates))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(explainer_agent.explain, request, res, breakdown)
            for res, breakdown, _ in candidates
        ]
        return [item.result() for item in futures]


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
        # Information only (blocked road, status update): nothing to dispatch.
        if request.type == IncidentType.INFO:
            return []
        # Likely hoax: held for the coordinator, never matched, no route.
        if request.hoax_reason or {"hoax", "likely_hoax"} & set(request.flags or []):
            return []
        # A team that has not checked in for 90 min is not offered as available.
        resources = [r for r in resources if not _stale(r)]
        resources = sorted(resources, key=lambda res: res.id)
        # A team already sent to another case is busy: never offered again until it is free.
        resources = [r for r in resources if not (getattr(r, "assigned_request_id", None) and r.assigned_request_id != request.id)]
        # A possible duplicate never gets the same team its twin is already being offered.
        twin_hint = getattr(request, "possible_duplicate", None)
        if twin_hint is not None and twin_hint.target_id:
            twin_matches = [m for m in storage_service.list_matches_for_request(twin_hint.target_id) if m.resource_id]
            twin_best = max(twin_matches, key=lambda m: m.score).resource_id if twin_matches else None
            twin = storage_service.get_request(twin_hint.target_id) if twin_best is None else None
            if twin is not None and getattr(twin, "possible_duplicate", None) is None:
                # The twin's list was never opened: work out its best team without saving anything.
                preview = self.find_matches(twin, top_n=1, save_to_storage=False)
                twin_best = preview[0].resource_id if preview else None
            if twin_best:
                resources = [r for r in resources if r.id != twin_best]

        scored_candidates = []
        people_needed = request.people_count if request.people_count else 1

        for res in resources:
            breakdown = scoring_engine.compute_match_score(request, res, fallback_ok=False)
            if breakdown is None:
                continue
            scored_candidates.append((res, breakdown, False))
        # Medical case cut off by water: a boat is the only way in, so rescue boats are offered too.
        if request.type == IncidentType.MEDICAL and (needs_water_access(request) or deep_water(request)):
            as_rescue = request.model_copy(update={"type": IncidentType.RESCUE})
            for res in resources:
                if travel_mode_for(res) != "water":
                    continue
                breakdown = scoring_engine.compute_match_score(as_rescue, res, fallback_ok=False)
                # Boats for a medical case only when they are close; a far boat is a no-team option instead.
                if breakdown is not None and breakdown.distance_km <= 10:
                    scored_candidates.append((res, breakdown, False))

        # No suitable free team: offer nothing rather than a busy team or the wrong kind of team.
        # The case card then shows "No suitable free team right now".
        using_fallback = False

        # Deep water (chest-deep or worse, or a roof): only boats can reach them, whatever the need.
        if deep_water(request):
            scored_candidates = [c for c in scored_candidates if travel_mode_for(c[0]) == "water"]

        # Distance score is 0 past 10 km, so a far team with more seats can outrank a nearer one.
        # Keep teams near the closest suitable team, inside this need's own kilometre limit.
        scored_candidates = _keep_nearer(scored_candidates, offer_limit_km(request))

        # Rank by arrival time first (boats by water, land teams by road estimate), then by seat fit.
        def _rank(item):
            res, breakdown, _ = item
            speed = BOAT_KMH if travel_mode_for(res) == "water" else LAND_KMH
            eta = breakdown.distance_km / speed
            fits = 0 if res.capacity_remaining >= people_needed else 1
            # Water depth from the report: deep water puts boats first, shallow water ground teams.
            from app.agents.depth import depth_rank
            return (depth_rank(request, res), round(eta * 60), fits, -breakdown.total_score, res.id)

        scored_candidates.sort(key=_rank)
        top_candidates = scored_candidates[:top_n]
        fallback_label = _fallback_label(request.type) if using_fallback else None
        wait_minutes, wait_team_name = (None, None)
        if using_fallback:
            wait_minutes, wait_team_name = _nearest_finish(request, resources)

        proposals: List[MatchProposal] = []
        explanations = _explain_together(request, top_candidates)
        for (res, breakdown, is_fallback), explanation in zip(top_candidates, explanations):
            # Check if there is an existing match in storage
            existing = [
                m
                for m in storage_service.list_matches_for_request(request.id)
                if m.resource_id == res.id
            ]

            is_overcommit = people_needed > res.capacity_remaining

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
                    eta_minutes=(eta_for_distance(breakdown.distance_km, travel_mode_for(res))
                                 if request.lat is not None and request.lng is not None else None),
                    travel_mode=travel_mode_for(res),
                    no_nearby=breakdown.distance_km > NEARBY_KM,
                    wait_minutes=wait_minutes if is_fallback else None,
                    wait_team_name=wait_team_name if is_fallback else None,
                    route_note=route_compare_note(breakdown.distance_km, travel_mode_for(res)),
                )
            )

        logger.info(
            "MatchingAgent: Generated %d match proposals for request %s",
            len(proposals),
            request.id,
        )
        return proposals


# One response radius for every need: offer, quote an ETA and explain "no team" with the same number.
RESPONSE_RADIUS_KM = 15.0
# Quote a minute ETA only inside this radius. Farther than this, say there is no nearby team.
NEARBY_KM = RESPONSE_RADIUS_KM
# A team inside this radius is close enough to prefer over a farther cluster.
PRACTICAL_KM = 40.0
# Rescue boats farther than this are not offered; the card then says no suitable team nearby.
BOAT_MAX_KM = RESPONSE_RADIUS_KM
# Medical teams use their own radius. It is not applied to rescue.
MEDICAL_MAX_KM = RESPONSE_RADIUS_KM
# Kept so older callers still import a single offer cap. Per-need limits are offer_limit_km.
MAX_OFFER_KM = MEDICAL_MAX_KM


# Land teams: straight-line km at 20 km/h (a road estimate; the map shows the real drive time).
LAND_KMH = 20.0
# Boats: straight line over flood water. Rescue boats move slowly through debris and current.
BOAT_KMH = 10.0


def travel_mode_for(res) -> str:
    kind = getattr(res, "kind", None)
    return "water" if getattr(kind, "value", kind) == ResourceKind.BOAT.value else "road"


def eta_for_distance(distance_km: float, mode: str = "road") -> Optional[int]:
    """Minutes for a straight-line leg: boats at BOAT_KMH by water, land teams at LAND_KMH.
    None when the team is too far to quote."""
    if distance_km > NEARBY_KM:
        return None
    speed = BOAT_KMH if mode == "water" else LAND_KMH
    return max(1, round((distance_km / speed) * 60))


def route_compare_note(distance_km: float, mode: str) -> Optional[str]:
    """Boat vs road using the same measured distance. Does not invent road closures."""
    if distance_km is None or distance_km < 0:
        return None
    water_min = max(1, round((distance_km / BOAT_KMH) * 60))
    road_min = max(1, round((distance_km / LAND_KMH) * 60))
    km = round(distance_km, 1)
    if mode == "water":
        return (
            f"Boat team: {km} km by water, about {water_min} min. A boat can reach people cut off by "
            f"flood water; by road it would be about {road_min} min, but only if roads are open "
            f"(straight-line estimate; no live road-closure feed)."
        )
    return (
        f"Road team: {km} km by road, about {road_min} min (a boat would need about {water_min} min). "
        f"Straight-line estimate; no live road-closure feed."
    )


# How much farther than the nearest team we still offer as an alternative.
NEAR_BAND_KM = 15.0


STALE_MIN = 90


def _stale(res) -> bool:
    from datetime import datetime, timezone
    stamp = getattr(res, "location_updated_at", None)
    if not stamp:
        return False
    try:
        last = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() > STALE_MIN * 60


_DEEP_BANDS = {"chest", "neck", "head", "above_head", "roof", "submerged"}


def deep_water(request: StoredRequest) -> bool:
    """Chest-deep or worse, from the depth reading or the report's own words."""
    depth = getattr(request, "water_depth", None) or {}
    band = (depth.get("band") if isinstance(depth, dict) else getattr(depth, "band", None)) or ""
    if band in _DEEP_BANDS:
        return True
    text = " ".join(filter(None, [request.raw_text, request.summary, request.ai_translation])).lower()
    return any(w in text for w in ("chest-deep", "chest deep", "neck-deep", "neck deep", "marooned", "roof", "terrace", "chhat", "chat par"))


def needs_water_access(request: StoredRequest) -> bool:
    """Trapped by water, or the report asks for a boat."""
    hazard = getattr(getattr(request, "hazard", None), "value", "")
    text = " ".join(filter(None, [request.raw_text, request.summary, request.ai_translation])).lower()
    return hazard in ("water_rising", "stranded") or any(w in text for w in ("boat", "naav", "nav bhejo", "trapped", "cut off"))


def offer_limit_km(request) -> float:
    """Medical stays at 25 km (10 km in deep water). Rescue is not capped by the medical radius."""
    kind = getattr(getattr(request, "type", None), "value", getattr(request, "type", None))
    if kind == "medical":
        return RESPONSE_RADIUS_KM
    return RESPONSE_RADIUS_KM


def water_access_case(request) -> bool:
    """Jetty, ferry, ghat, or someone already in the water. A road ambulance cannot reach them."""
    place = getattr(request, "place_text", None) or ""
    text = " ".join(filter(None, [getattr(request, "raw_text", None), getattr(request, "summary", None), place]))
    return bool(re.search(r"jetty|ferry|\bghat\b|ജെട്ടി|घाट|boat jetty|in the water", text, flags=re.I))


def _keep_nearer(scored: list, limit_km: float = MEDICAL_MAX_KM) -> list:
    # Never offer a team beyond this need's limit: the no-team options show the farther ones honestly.
    scored = [item for item in scored if item[1].distance_km <= limit_km]
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
        speed = BOAT_KMH if travel_mode_for(res) == "water" else LAND_KMH
        travel = max(1, round((dist / speed) * 60))
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
        from app.tools.geo import team_distance_km
        return team_distance_km(request, res) or 0.0

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
