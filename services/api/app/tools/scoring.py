import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.models.schemas import HazardType, IncidentType, VulnerableFlags
from app.models.firestore_models import StoredRequest

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


class ScoringEngine:
    def __init__(self):
        self.weights = UrgencyWeights()

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

        # 6. Confidence discount, then a fixed type priority.
        # Rescue and medical outrank food or info of a similar size.
        conf = req.confidence
        avg_conf = (
            conf.type + conf.place + conf.people + conf.vulnerable + conf.urgency
        ) / 5.0
        discount = 1.0 - ((1.0 - avg_conf) * w.confidence_discount_factor)
        type_bonus = {
            IncidentType.MEDICAL: 16.0,
            IncidentType.RESCUE: 12.0,
            IncidentType.SHELTER: 2.0,
        }.get(req.type, 0.0)
        final_score = round(max(0.0, min(100.0, raw_weighted * discount * 100.0 + type_bonus)), 1)
        # A hoax or spam copy is kept, but it must not sit in Needs help now (score >= 75).
        if any(flag in (req.flags or []) for flag in ("hoax", "hoax_or_flood")):
            final_score = min(final_score, 40.0)
            reasons_parts.append("flagged as hoax or spam")

        breakdown = {
            "vulnerability": round(v_score * 100, 1),
            "people": round(p_score * 100, 1),
            "hazard": round(h_score * 100, 1),
            "wait_time": round(w_score * 100, 1),
            "wait_points": round(w.w_wait_time * w_score * discount * 100.0, 1),
            "wait_minutes": int(wait_minutes),
            "confidence_factor": round(discount, 3),
            "type_priority": type_bonus,
            "final_score": final_score,
        }

        reason_text = " + ".join(reasons_parts) if reasons_parts else "General relief request"
        reason_text += f" (Urgency score: {final_score})"

        return UrgencyScoreResult(
            score=final_score,
            breakdown=breakdown,
            reason=reason_text,
        )

    def compute_match_score(
        self, req: StoredRequest, res: "StoredResource", fallback_ok: bool = False, soon_free: bool = False
    ) -> Optional["MatchBreakdown"]:
        from app.models.firestore_models import ResourceKind, ResourceStatus, MatchBreakdown
        from app.models.schemas import IncidentType
        from app.tools.geo import haversine_distance

        # Hard constraint 1: Capacity remaining must be > 0
        if res.capacity_remaining <= 0:
            return None

        # Primary kinds only. A shelter is not a boat. Fallbacks are explicit.
        primary = {
            IncidentType.RESCUE: [ResourceKind.BOAT],
            IncidentType.MEDICAL: [ResourceKind.MEDICAL],
            IncidentType.FOOD: [ResourceKind.FOOD],
            IncidentType.SHELTER: [ResourceKind.SHELTER],
            IncidentType.ANIMAL_ATTACK: [ResourceKind.MEDICAL],
            IncidentType.INFO: [ResourceKind.SHELTER, ResourceKind.FOOD],
            IncidentType.OTHER: [ResourceKind.SHELTER, ResourceKind.FOOD, ResourceKind.BOAT],
        }
        fallback = {
            IncidentType.RESCUE: [ResourceKind.SHELTER],
            IncidentType.MEDICAL: [ResourceKind.SHELTER],
            IncidentType.FOOD: [ResourceKind.SHELTER],
            IncidentType.SHELTER: [ResourceKind.FOOD],
        }
        allowed = fallback.get(req.type, []) if fallback_ok else primary.get(req.type, [])
        if res.kind not in allowed:
            return None
        if res.status not in (ResourceStatus.AVAILABLE,) and not fallback_ok and not soon_free:
            return None

        # 1. Distance score (max 30 pts)
        if req.lat is not None and req.lng is not None:
            dist_km = haversine_distance(req.lat, req.lng, res.lat, res.lng)
        else:
            dist_km = 2.5

        if dist_km <= 0.5:
            dist_score = 30.0
        else:
            dist_score = round(max(0.0, 30.0 * (1.0 - min(dist_km, 10.0) / 10.0)), 1)

        # 2. Capacity fit score (max 25 pts)
        needed = req.people_count if req.people_count else 1
        if res.capacity_remaining >= needed:
            cap_score = 25.0
        else:
            cap_score = round(25.0 * (res.capacity_remaining / max(1, needed)), 1)

        # 3. Urgency score (max 25 pts)
        urg_score = round(25.0 * (req.urgency_score / 100.0), 1)

        # 4. Vulnerability fit score (max 20 pts)
        v = req.vulnerable
        has_vuln = v.child or v.elderly or v.disabled or v.pregnant or v.medical_need
        if v.medical_need and res.kind == ResourceKind.MEDICAL:
            vuln_score = 20.0
        elif (v.child or v.elderly or v.pregnant or v.disabled) and res.kind in [
            ResourceKind.BOAT,
            ResourceKind.SHELTER,
        ]:
            vuln_score = 20.0
        elif has_vuln:
            vuln_score = 15.0
        else:
            vuln_score = 10.0

        total = round(dist_score + cap_score + urg_score + vuln_score, 1)

        return MatchBreakdown(
            distance_km=round(dist_km, 2),
            distance_score=dist_score,
            capacity_fit_score=cap_score,
            urgency_score=urg_score,
            vulnerability_fit_score=vuln_score,
            total_score=total,
        )


scoring_engine = ScoringEngine()

