import logging
import math
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.models.schemas import HazardType, IncidentType, VulnerableFlags
from app.models.firestore_models import StoredRequest

logger = logging.getLogger("relief_desk.scoring")


class UrgencyWeights(BaseModel):
    """Within-tier weights. Tier floors (Immediate 80, Urgent 60) are applied first."""
    version: int = 2
    w_vulnerability: float = Field(default=0.30, ge=0.0, le=1.0)
    w_people: float = Field(default=0.15, ge=0.0, le=1.0)
    w_hazard: float = Field(default=0.30, ge=0.0, le=1.0)
    w_wait_time: float = Field(default=0.20, ge=0.0, le=1.0)
    w_isolation: float = Field(default=0.05, ge=0.0, le=1.0)
    # Kept for the weights editor. Low confidence no longer lowers the score; it adds "verify".
    confidence_discount_factor: float = Field(default=0.0, ge=0.0, le=1.0)
    v_child: float = 0.85
    v_elderly: float = 0.85
    v_disabled: float = 0.9
    v_pregnant: float = 0.85
    v_medical: float = 1.0


class UrgencyScoreResult(BaseModel):
    score: float
    breakdown: Dict[str, float]
    reason: str
    tier: str = "standard"
    verify: bool = False


TIER_IMMEDIATE = 80.0
TIER_URGENT = 60.0
# Below this average field confidence the case gets a "verify" flag.
VERIFY_BELOW = 0.6
WAIT_TAU_MIN = 180.0

_IN_WATER = re.compile(
    r"in the water|into the water|water (?:is )?(?:inside|entering|coming in|in the house|in our house)|"
    r"(?:neck|chest|waist)[- ]deep|swept away|drowning|being carried|"
    r"\u092a\u093e\u0928\u0940 \u0918\u0930 \u092e\u0947\u0902|doob|ghar mein paani|andar paani",
    re.I,
)
_TRAPPED = re.compile(r"trapped|stuck|can'?t get out|cannot get out|unable to (?:leave|get out|move)|phanse|phas", re.I)
_SEVERE_INJURY = re.compile(r"bleeding|unconscious|not breathing|can'?t breathe|breathing (?:difficulty|problem)|unresponsive|fainted", re.I)
_LIFE_SUPPORT = re.compile(r"oxygen|dialysis|insulin|ventilator|\u0911\u0915\u094d\u0938\u0940\u091c\u0928", re.I)
_LABOUR = re.compile(r"labou?r pain|in labou?r|contractions|water broke|delivery pain|\u092a\u094d\u0930\u0938\u0935", re.I)
_ROOF = re.compile(
    r"roof|terrace|upper floor|first floor|second floor|top floor|chhat|chat par|"
    r"\u091b\u0924|\u092e\u0941\u0915\u0933\u093f\u0932\u094d",
    re.I,
)
_WINDOW_WATER = re.compile(
    r"window[- ]level|water (?:at|up to) (?:the )?windows?|windows? level|"
    r"rising (?:water|flood)|water (?:is )?rising|"
    r"khidki|khirk[ie]|paani badh|pani badh|"
    r"\u0916\u093f\u0921\u093c\u0915\u0940|\u0916\u093f\u0921\u0915\u0940|\u092a\u093e\u0928\u0940 \u092c\u0922\u093c",
    re.I,
)
_BOAT_RESCUE = re.compile(
    r"need(?:s|ed)? a (?:rescue )?boat|send (?:a |the )?(?:rescue )?boat|boat rescue|"
    r"rescue boat|naav bhej|nauka|boat (?:bhej|chahiye)|"
    r"\u0928\u093e\u0935|\u092c\u094b\u091f \u092d\u0947\u091c",
    re.I,
)
_NO_SUPPLY = re.compile(r"no (?:food|drinking water|water to drink|clean water)|without (?:food|water)|nothing to eat|khana nahi|paani nahi", re.I)
_LONG = re.compile(r"since yesterday|since last night|(?:1[2-9]|[2-9]\d) hours|\d+ days?|two days|whole day|kal se", re.I)
_ISOLATED = re.compile(r"cut off|isolated|no road|road (?:washed|blocked|gone)|bridge (?:collapsed|gone|washed)|unreachable|no access|no way out", re.I)


def _text_of(req: StoredRequest) -> str:
    parts = [req.raw_text or "", req.summary or "", req.ai_translation or "", req.place_text or ""]
    parts += list((req.translations or {}).values())
    return " ".join(p for p in parts if p)


class ScoringEngine:
    def __init__(self):
        self.weights = UrgencyWeights()

    def update_weights(self, new_weights: UrgencyWeights) -> UrgencyWeights:
        new_weights.version = self.weights.version + 1
        self.weights = new_weights
        logger.info("Updated urgency weights to version %d", self.weights.version)
        return self.weights

    def tier_for(self, req: StoredRequest, text: str, wait_minutes: float) -> Tuple[str, str]:
        """Triage first (SALT/START style): fixed categories by obvious life threat."""
        v = req.vulnerable
        in_water = bool(_IN_WATER.search(text))
        if in_water:
            return "immediate", "people are in the water or water is entering the home"
        if req.hazard == HazardType.WATER_RISING and _TRAPPED.search(text):
            return "immediate", "people are trapped and the water is rising"
        if req.hazard == HazardType.INJURY and _SEVERE_INJURY.search(text):
            return "immediate", "a serious injury: bleeding, breathing trouble or unresponsive"
        if _SEVERE_INJURY.search(text) and re.search(r"unconscious|not breathing|unresponsive", text, re.I):
            return "immediate", "someone is unresponsive or not breathing"
        if _LIFE_SUPPORT.search(text):
            return "immediate", "someone depends on oxygen, dialysis or insulin"
        if v.pregnant and _LABOUR.search(text):
            return "immediate", "a pregnant woman is in labour"
        vulnerable_stuck = v.child or v.elderly or v.disabled
        stranded = req.hazard in (HazardType.STRANDED, HazardType.WATER_RISING) or bool(_ROOF.search(text))
        if vulnerable_stuck and stranded:
            who = ", ".join(n for n, on in (("a child", v.child), ("an elderly person", v.elderly), ("a disabled person", v.disabled)) if on)
            where = "in rising water" if req.hazard == HazardType.WATER_RISING else "stranded"
            return "urgent", f"{who} {where}"
        roofed = bool(_ROOF.search(text))
        window_or_rising = bool(_WINDOW_WATER.search(text)) or req.hazard == HazardType.WATER_RISING
        if roofed and window_or_rising:
            return "urgent", "adults stranded on a roof or upper floor with water at window level or rising"
        if _BOAT_RESCUE.search(text) and (
            roofed
            or req.type == IncidentType.RESCUE
            or req.hazard in (HazardType.STRANDED, HazardType.WATER_RISING)
        ):
            return "urgent", "boat rescue requested"
        if _NO_SUPPLY.search(text) and (wait_minutes >= 720 or _LONG.search(text)):
            return "urgent", "no water or food for over 12 hours"
        return "standard", ""

    def compute_urgency(
        self,
        req: StoredRequest,
        custom_weights: Optional[UrgencyWeights] = None,
        now: Optional[datetime] = None,
    ) -> UrgencyScoreResult:
        w = custom_weights or self.weights
        reasons_parts: List[str] = []
        text = _text_of(req)

        # Vulnerability: the strongest single flag, plus 0.1 for each extra flag, capped at 1.
        v = req.vulnerable
        flags = [(name, val) for name, on, val in (
            ("child", v.child, w.v_child),
            ("elderly", v.elderly, w.v_elderly),
            ("disabled", v.disabled, w.v_disabled),
            ("pregnant", v.pregnant, w.v_pregnant),
            ("medical need", v.medical_need, w.v_medical),
        ) if on]
        v_score = min(1.0, max(val for _, val in flags) + 0.1 * (len(flags) - 1)) if flags else 0.0
        if flags:
            reasons_parts.append("vulnerable: " + ", ".join(n for n, _ in flags))

        # People: log scale so one person is not penalised. 50 people -> 1.0.
        count = req.people_count if req.people_count is not None else 1
        p_score = min(1.0, math.log2(1 + max(1, count)) / math.log2(51))
        # Score as one person when unknown, but never claim a count the report did not give.
        reasons_parts.append("people not stated" if not req.people_count else f"{count} person{'s' if count != 1 else ''}")

        # Hazard.
        in_water = bool(_IN_WATER.search(text))
        hazard_map = {
            HazardType.WATER_RISING: (0.9, "water rising"),
            HazardType.INJURY: (0.85, "injury"),
            HazardType.STRANDED: (0.6, "stranded"),
            HazardType.UNKNOWN: (0.5, "hazard not yet known"),
            HazardType.NONE: (0.1, "no immediate hazard"),
        }
        h_score, h_desc = (1.0, "in the water") if in_water else hazard_map.get(req.hazard, (0.5, "hazard not yet known"))
        if req.hazard != HazardType.NONE or in_water:
            reasons_parts.append(h_desc)

        # Waiting time keeps rising: 1 - e^(-m/180).
        current_time = now or datetime.now(timezone.utc)
        try:
            created_dt = datetime.fromisoformat(req.created_at)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            wait_minutes = max(0.0, (current_time - created_dt).total_seconds() / 60.0)
        except Exception:
            wait_minutes = 0.0
        w_score = 1.0 - math.exp(-wait_minutes / WAIT_TAU_MIN)
        if wait_minutes >= 30:
            reasons_parts.append(f"waiting {int(wait_minutes)} min")

        iso_score = 1.0 if _ISOLATED.search(text) else 0.0
        if iso_score:
            reasons_parts.append("cut off / no road access")

        raw = 100.0 * (
            w.w_hazard * h_score
            + w.w_vulnerability * v_score
            + w.w_people * p_score
            + w.w_wait_time * w_score
            + w.w_isolation * iso_score
        )
        raw = max(0.0, min(100.0, raw))

        tier, tier_reason = self.tier_for(req, text, wait_minutes)
        if tier == "immediate":
            final_score = TIER_IMMEDIATE + raw * (100.0 - TIER_IMMEDIATE) / 100.0
        elif tier == "urgent":
            final_score = min(TIER_IMMEDIATE - 0.1, TIER_URGENT + raw * (TIER_IMMEDIATE - TIER_URGENT) / 100.0)
        else:
            final_score = raw
        final_score = round(max(0.0, min(100.0, final_score)), 1)

        # Low confidence never lowers urgency. It asks the coordinator to verify.
        conf = req.confidence
        avg_conf = (conf.type + conf.place + conf.people + conf.vulnerable + conf.urgency) / 5.0
        verify = avg_conf < VERIFY_BELOW
        if verify and "verify" not in (req.flags or []):
            req.flags = list(req.flags or []) + ["verify"]

        # A hoax or spam copy is kept, but it must not sit in Needs help now.
        hoax = any(flag in (req.flags or []) for flag in ("hoax", "hoax_or_flood", "likely_hoax"))
        if hoax:
            final_score = min(final_score, 40.0)

        breakdown = {
            "vulnerability": round(v_score * 100, 1),
            "people": round(p_score * 100, 1),
            "hazard": round(h_score * 100, 1),
            "wait_time": round(w_score * 100, 1),
            "isolation": round(iso_score * 100, 1),
            "wait_points": round(w.w_wait_time * w_score * 100.0, 1),
            "wait_minutes": int(wait_minutes),
            "confidence_factor": round(avg_conf, 3),
            "within_tier": round(raw, 1),
            "tier_floor": TIER_IMMEDIATE if tier == "immediate" else (TIER_URGENT if tier == "urgent" else 0.0),
            "verify": 1.0 if verify else 0.0,
            "final_score": final_score,
        }

        if tier == "immediate":
            lead = f"Immediate: {tier_reason}."
        elif tier == "urgent":
            lead = f"Urgent: {tier_reason}."
        else:
            lead = "Standard priority: no immediate life threat reported."
        detail = "; ".join(reasons_parts) if reasons_parts else "general relief request"
        reason_text = f"{lead} Order within the tier: {detail}."
        if hoax:
            reason_text += " Flagged as possible hoax or spam, so capped at 40."
        if verify:
            reason_text += " Please verify: the report is unclear, so priority was kept, not lowered."
        reason_text += f" (Urgency score: {final_score})"

        return UrgencyScoreResult(
            score=final_score,
            breakdown=breakdown,
            reason=reason_text,
            tier=tier,
            verify=verify,
        )

    def compute_match_score(
        self, req: StoredRequest, res: "StoredResource", fallback_ok: bool = False
    ) -> Optional["MatchBreakdown"]:
        from app.models.firestore_models import ResourceKind, ResourceStatus, MatchBreakdown
        from app.models.schemas import IncidentType
        from app.tools.geo import haversine_distance

        from app.tools.inventory import missing_supplies
        if missing_supplies(req, res):
            return None

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
            IncidentType.OTHER: [ResourceKind.SHELTER, ResourceKind.FOOD],
        }
        # No cross-type fallback: a shelter van is never offered for a rooftop rescue.
        # fallback_ok is kept for callers but no longer widens the kinds or the status.
        allowed = primary.get(req.type, [])
        if res.kind not in allowed:
            return None
        # Free teams only: busy, en route, on scene, returning, depleted or held teams are never offered.
        if res.status != ResourceStatus.AVAILABLE or res.hold_request_id:
            return None

        # 1. Distance score (max 30 pts)
        if req.lat is not None and req.lng is not None:
            dist_km = haversine_distance(req.lat, req.lng, res.lat, res.lng)
        else:
            # No location: distance is unknown, so no team is offered on a made-up distance.
            return None

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

