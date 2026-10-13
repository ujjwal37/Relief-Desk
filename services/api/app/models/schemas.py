from __future__ import annotations
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class AiCall(BaseModel):
    """One model attempt. provider is gemini, cache, or fallback."""

    provider: str = "fallback"
    model: Optional[str] = None
    latency_ms: int = 0
    tokens: Optional[int] = None
    cached: bool = False
    fallback_reason: Optional[str] = None

    def badge(self) -> str:
        if self.provider == "cache" or self.cached:
            return "recorded"
        if self.provider == "gemini":
            return "gemini"
        if self.provider == "antigravity-local":
            return "local"
        return "offline"


class IncidentType(str, Enum):
    RESCUE = "rescue"
    FOOD = "food"
    MEDICAL = "medical"
    SHELTER = "shelter"
    INFO = "info"
    ANIMAL_ATTACK = "animal_attack"
    OTHER = "other"


class HazardType(str, Enum):
    WATER_RISING = "water_rising"
    STRANDED = "stranded"
    INJURY = "injury"
    NONE = "none"
    UNKNOWN = "unknown"


class UrgencyHint(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SupportedLanguage(str, Enum):
    HI = "hi"
    HINGLISH = "hinglish"
    EN = "en"
    ML = "ml"


class DedupeDecisionType(str, Enum):
    NEW = "new"
    DUPLICATE = "duplicate"
    UPDATE = "update"
    CONFLICT = "conflict"


class PeopleInfo(BaseModel):
    count: Optional[int] = Field(default=None, description="Number of people requiring relief, 0 to 500")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in people count [0, 1]")

    @field_validator("count")
    @classmethod
    def validate_count_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 0 or v > 500):
            raise ValueError(f"People count must be between 0 and 500, got {v}")
        return v


class VulnerableFlags(BaseModel):
    child: bool = False
    elderly: bool = False
    disabled: bool = False
    pregnant: bool = False
    medical_need: bool = False


class FieldConfidences(BaseModel):
    type: float = Field(default=1.0, ge=0.0, le=1.0)
    place: float = Field(default=1.0, ge=0.0, le=1.0)
    people: float = Field(default=1.0, ge=0.0, le=1.0)
    vulnerable: float = Field(default=1.0, ge=0.0, le=1.0)
    urgency: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractedRequest(BaseModel):
    type: IncidentType = Field(default=IncidentType.OTHER)
    secondary_needs: List[IncidentType] = Field(default_factory=list)
    place_text: Optional[str] = Field(default=None, max_length=500)
    people: PeopleInfo = Field(default_factory=PeopleInfo)
    vulnerable: VulnerableFlags = Field(default_factory=VulnerableFlags)
    hazard: HazardType = Field(default=HazardType.UNKNOWN)
    urgency_hint: UrgencyHint = Field(default=UrgencyHint.MEDIUM)
    language: SupportedLanguage = Field(default=SupportedLanguage.EN)
    is_update_phrase: bool = False
    confidence: FieldConfidences = Field(default_factory=FieldConfidences)
    evidence_spans: Dict[str, str] = Field(default_factory=dict)
    notes: str = Field(default="")
    needs_human_review: bool = False
    ward_id: Optional[str] = None
    hoax_score: float = Field(default=0.0, ge=0.0, le=1.0)
    original_text: str = ""

    def validate_spans_against_raw(self, raw_text: str) -> None:
        """Validates evidence_spans against raw_text substrings.
        If a span is not found in raw_text, lowers the field confidence and flags it."""
        if not raw_text:
            return
        raw_lower = raw_text.lower()
        for field_name, span in list(self.evidence_spans.items()):
            if span and span.lower() not in raw_lower:
                if field_name == "people":
                    self.confidence.people = 0.0
                elif field_name == "vulnerable":
                    self.confidence.vulnerable = 0.0
                elif field_name == "type":
                    self.confidence.type = 0.0
                self.needs_human_review = True


class DedupeDecision(BaseModel):
    decision: DedupeDecisionType = Field(..., description="Deduplication decision")
    target_request_id: Optional[str] = Field(default=None, description="Candidate request ID merged into or updated")
    changed_fields: Dict[str, Any] = Field(default_factory=dict, description="Changed fields if decision is update")
    evidence: List[str] = Field(default_factory=list, description="List of concrete evidence reasons")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    distance_km: Optional[float] = None
    minutes_apart: Optional[float] = None
    # True when the pair is close but under the auto-merge threshold. The case stays separate.
    review: bool = False

    @model_validator(mode="after")
    def validate_decision_rules(self) -> DedupeDecision:
        if self.decision == DedupeDecisionType.UPDATE and not self.changed_fields:
            raise ValueError("Update decision requires non-empty changed_fields")
        if self.decision in (DedupeDecisionType.DUPLICATE, DedupeDecisionType.UPDATE, DedupeDecisionType.CONFLICT):
            if not self.target_request_id:
                raise ValueError(f"Decision '{self.decision.value}' requires target_request_id")
        return self


class Explanation(BaseModel):
    text_en: str = Field(..., min_length=3, description="English explanation (<= 2 sentences)")
    text_hi: Optional[str] = Field(default=None, description="Hindi explanation")

    def verify_numeric_consistency(self, allowed_numbers: List[float | int]) -> bool:
        """Guardrail: ensures every numeric token in explanation exists in allowed_numbers."""
        import re
        tokens = re.findall(r"\b\d+(?:\.\d+)?\b", self.text_en)
        allowed_set = {float(n) for n in allowed_numbers}
        for token in tokens:
            try:
                val = float(token)
                if val not in allowed_set:
                    return False
            except ValueError:
                continue
        return True
