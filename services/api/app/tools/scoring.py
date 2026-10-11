import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.models.schemas import HazardType, IncidentType
from app.models.firestore_models import ResourceKind, ResourceStatus, StoredRequest, StoredResource
from app.tools.geo import haversine_distance

logger = logging.getLogger("relief_desk.scoring")


class UrgencyWeights(BaseModel):
    version: int = 1
    w_vulnerability: float = Field(default=0.35, ge=0.0, le=1.0)
    w_people: float = Field(default=0.25, ge=0.0, le=1.0)
    w_hazard: float = Field(default=0.25, ge=0.0, le=1.0)
    w_wait_time: float = Field(default=0.15, ge=0.0, le=1.0)
    confidence_discount_factor: float = Field(default=0.20, ge=0.0, le=1.0)
    v_child: float = 1.0
    v_elderly: float = 1.0
    v_disabled: float = 1.0
    v_pregnant: float = 1.2
    v_medical: float = 1.2


class UrgencyScoreResult(BaseModel):
    score: float
    breakdown: Dict[str, float]
    reason: str


class MatchWeights(BaseModel):
    """Weights for scoring.match_score. Contributions are weight * factor * 100."""

    w_d: float = Field(default=0.30, ge=0.0, le=1.0)
    w_c: float = Field(default=0.25, ge=0.0, le=1.0)
    w_u: float = Field(default=0.25, ge=0.0, le=1.0)
    w_v: float = Field(default=0.20, ge=0.0, le=1.0)


class MatchScoreResult(BaseModel):
    score: float
    eligible: bool
    hard_constraint: Optional[str] = None
    overcommit_risk: bool = False
    breakdown: Dict[str, float]
    distance_km: Optional[float] = None
    capacity_fit: float = 0.0
    dist_norm: float = 0.0
    urgency_norm: float = 0.0
    vuln_fit: float = 0.0
    people_requested: int = 0
    capacity_remaining: int = 0


# Hard type compatibility. Rescue may use a boat or a shelter so the
# coordinator can compare both. Medical also covers injury and animal attack.
COMPATIBLE_INCIDENT_TYPES = {
    ResourceKind.BOAT: frozenset({IncidentType.RESCUE}),
    ResourceKind.SHELTER: frozenset({IncidentType.SHELTER, IncidentType.RESCUE}),
    ResourceKind.FOOD: frozenset({IncidentType.FOOD}),
    ResourceKind.MEDICAL: frozenset({IncidentType.MEDICAL, IncidentType.ANIMAL_ATTACK}),
}

MAX_MATCH_KM = 12.0
UNKNOWN_DIST_NORM = 0.2


def people_demand(req: StoredRequest) -> int:
    """Capacity units requested. One person uses one seat, bed, meal, or slot."""
    if req.people_count is None:
        return 1
    return max(0, int(req.people_count))


def is_type_compatible(req: StoredRequest, kind: ResourceKind) -> bool:
    if kind == ResourceKind.MEDICAL and (
        req.vulnerable.medical_need or req.hazard == HazardType.INJURY
    ):
        return True
    return req.type in COMPATIBLE_INCIDENT_TYPES.get(kind, frozenset())


def _vulnerability_fit(req: StoredRequest, kind: ResourceKind) -> float:
    flags = req.vulnerable
    vuln_count = sum(
        1
        for present in (
            flags.child,
            flags.elderly,
            flags.disabled,
            flags.pregnant,
            flags.medical_need,
        )
        if present
    )
    if kind == ResourceKind.BOAT:
        if req.hazard in (HazardType.WATER_RISING, HazardType.STRANDED):
            return 1.0
        if req.type == IncidentType.RESCUE:
            return 0.6
        return 0.3
    if kind == ResourceKind.SHELTER:
        base = 0.7 if req.type == IncidentType.SHELTER else 0.45
        boost = min(0.3, 0.1 * vuln_count)
        if flags.child or flags.elderly or flags.pregnant or flags.disabled:
            boost = max(boost, 0.2)
        return min(1.0, base + boost)
    if kind == ResourceKind.MEDICAL:
        if flags.medical_need:
            return 1.0
        if req.hazard == HazardType.INJURY or req.type == IncidentType.ANIMAL_ATTACK:
            return 0.9
        if req.type == IncidentType.MEDICAL:
            return 0.85
        return 0.4
    if kind == ResourceKind.FOOD:
        base = 0.8 if req.type == IncidentType.FOOD else 0.35
        if vuln_count:
            return min(1.0, base + 0.1)
        return base
    return 0.0


def _weighted_parts(
    weights: MatchWeights,
    dist_norm: float,
    capacity_fit: float,
    urgency_norm: float,
    vuln_fit: float,
) -> Tuple[Dict[str, float], float]:
    raw = {
        "dist": weights.w_d * dist_norm * 100.0,
        "capacity": weights.w_c * capacity_fit * 100.0,
        "urgency": weights.w_u * urgency_norm * 100.0,
        "vuln": weights.w_v * vuln_fit * 100.0,
    }
    parts = {key: round(value, 1) for key, value in raw.items()}
    score = round(sum(parts.values()), 1)
    return parts, score


def _ineligible(
    reason: str,
    people: int,
    remaining: int,
    distance_km: Optional[float] = None,
) -> MatchScoreResult:
    return MatchScoreResult(
        score=0.0,
        eligible=False,
        hard_constraint=reason,
        overcommit_risk=False,
        breakdown={"dist": 0.0, "capacity": 0.0, "urgency": 0.0, "vuln": 0.0},
        distance_km=distance_km,
        people_requested=people,
        capacity_remaining=remaining,
    )


class ScoringEngine:
    def __init__(self):
        self.weights = UrgencyWeights()
        self.match_weights = MatchWeights()

    def update_weights(self, new_weights: UrgencyWeights) -> UrgencyWeights:
        new_weights.version = self.weights.version + 1
        self.weights = new_weights
        logger.info("Updated urgency weights to version %d", self.weights.version)
        return self.weights

    def compute_urgency(
        self,
        req: StoredRequest,
        custom_weights: Optional[UrgencyWeights] = None,
        now: Optional[datetime] = None,
    ) -> UrgencyScoreResult:
        w = custom_weights or self.weights
        reasons_parts: List[str] = []

        # 1. Vulnerability score (0.0 to 1.0)
        v = req.vulnerable
        v_points = 0.0
        v_active = []
        if v.child:
            v_points += w.v_child
            v_active.append("child")
        if v.elderly:
            v_points += w.v_elderly
            v_active.append("elderly")
        if v.disabled:
            v_points += w.v_disabled
            v_active.append("disabled")
        if v.pregnant:
            v_points += w.v_pregnant
            v_active.append("pregnant")
        if v.medical_need:
            v_points += w.v_medical
            v_active.append("medical need")

        # Normalize vulnerability to [0, 1] assuming max typical points is ~3.0
        v_score = min(1.0, v_points / 2.5) if v_points > 0 else 0.0
        if v_active:
            reasons_parts.append(f"Vulnerable flags: {', '.join(v_active)}")

        # 2. People count score (0.0 to 1.0)
        count = req.people_count if req.people_count is not None else 1
        # Diminishing returns scaling: 1 person -> 0.1, 5 -> 0.45, 20+ -> 1.0
        p_score = min(1.0, math.sqrt(max(1, count)) / math.sqrt(25))
        reasons_parts.append(f"{count} person{'s' if count != 1 else ''}")

        # 3. Hazard score (0.0 to 1.0)
        hazard_map = {
            HazardType.WATER_RISING: (1.0, "water rising rapidly"),
            HazardType.STRANDED: (0.8, "stranded on structure"),
            HazardType.INJURY: (0.85, "acute injuries"),
            HazardType.UNKNOWN: (0.4, "unassessed hazard"),
            HazardType.NONE: (0.1, "no immediate hazard"),
        }
        h_score, h_desc = hazard_map.get(req.hazard, (0.4, "unknown hazard"))
        if req.hazard != HazardType.NONE:
            reasons_parts.append(h_desc)

        # 4. Wait time score (0.0 to 1.0)
        current_time = now or datetime.now(timezone.utc)
        try:
            created_dt = datetime.fromisoformat(req.created_at)
            wait_minutes = max(0.0, (current_time - created_dt).total_seconds() / 60.0)
        except Exception:
            wait_minutes = 0.0
        # 120 minutes waiting scales to 1.0
        w_score = min(1.0, wait_minutes / 120.0)
        if wait_minutes >= 30:
            reasons_parts.append(f"waiting {int(wait_minutes)}m")

        # 5. Base weighted score
        raw_weighted = (
            (w.w_vulnerability * v_score)
            + (w.w_people * p_score)
            + (w.w_hazard * h_score)
            + (w.w_wait_time * w_score)
        )

        # 6. Confidence discount
        conf = req.confidence
        avg_conf = (
            conf.type + conf.place + conf.people + conf.vulnerable + conf.urgency
        ) / 5.0
        discount = 1.0 - ((1.0 - avg_conf) * w.confidence_discount_factor)
        final_score = round(max(0.0, min(100.0, raw_weighted * discount * 100.0)), 1)

        breakdown = {
            "vulnerability": round(v_score * 100, 1),
            "people": round(p_score * 100, 1),
            "hazard": round(h_score * 100, 1),
            "wait_time": round(w_score * 100, 1),
            "confidence_factor": round(discount, 3),
            "final_score": final_score,
        }

        reason_text = " + ".join(reasons_parts) if reasons_parts else "General relief request"
        reason_text += f" (Urgency score: {final_score})"

        return UrgencyScoreResult(
            score=final_score,
            breakdown=breakdown,
            reason=reason_text,
        )

    def match_score(
        self,
        req: StoredRequest,
        res: StoredResource,
        weights: Optional[MatchWeights] = None,
    ) -> MatchScoreResult:
        """Deterministic match score.

        score = w_d*dist_norm + w_c*capacity_fit + w_u*urgency + w_v*vuln_fit,
        scaled to 0-100. Hard constraints: type compatible and capacity > 0.
        The four breakdown parts sum to the score. No LLM is involved.
        """
        try:
            w = weights or self.match_weights
            demand = people_demand(req)
            remaining = int(res.capacity_remaining)

            distance_km: Optional[float] = None
            if None not in (req.lat, req.lng, res.lat, res.lng):
                distance_km = haversine_distance(req.lat, req.lng, res.lat, res.lng)

            if not is_type_compatible(req, res.kind):
                return _ineligible("type_incompatible", demand, remaining, distance_km)
            if res.status == ResourceStatus.OFFLINE:
                return _ineligible("offline", demand, remaining, distance_km)
            if remaining <= 0:
                return _ineligible("no_capacity", demand, remaining, distance_km)

            if distance_km is None:
                dist_norm = UNKNOWN_DIST_NORM
            else:
                dist_norm = max(0.0, min(1.0, 1.0 - (distance_km / MAX_MATCH_KM)))

            if demand <= 0:
                capacity_fit = 1.0
            else:
                capacity_fit = max(0.0, min(1.0, remaining / float(demand)))

            urgency_norm = max(0.0, min(1.0, float(req.urgency_score) / 100.0))
            vuln_fit = _vulnerability_fit(req, res.kind)
            parts, score = _weighted_parts(w, dist_norm, capacity_fit, urgency_norm, vuln_fit)
            return MatchScoreResult(
                score=score,
                eligible=True,
                hard_constraint=None,
                overcommit_risk=demand > remaining,
                breakdown=parts,
                distance_km=distance_km,
                capacity_fit=round(capacity_fit, 3),
                dist_norm=round(dist_norm, 3),
                urgency_norm=round(urgency_norm, 3),
                vuln_fit=round(vuln_fit, 3),
                people_requested=demand,
                capacity_remaining=remaining,
            )
        except Exception:
            logger.exception("match_score failed for request %s resource %s", req.id, res.id)
            raise


def match_score(
    req: StoredRequest,
    res: StoredResource,
    weights: Optional[MatchWeights] = None,
) -> MatchScoreResult:
    return scoring_engine.match_score(req, res, weights)


scoring_engine = ScoringEngine()
