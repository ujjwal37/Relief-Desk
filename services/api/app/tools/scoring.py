import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.models.schemas import HazardType, VulnerableFlags
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


scoring_engine = ScoringEngine()
