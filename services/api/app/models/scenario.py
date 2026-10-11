from __future__ import annotations
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class ScenarioTile(BaseModel):
    id: str
    label_en: str
    label_hi: Optional[str] = None
    incident_type: str
    icon: str = "help-circle"


class ScenarioConfig(BaseModel):
    id: str
    title: str
    description: str = ""
    incident_types: List[str] = Field(default_factory=list)
    tiles: List[ScenarioTile] = Field(default_factory=list)
    follow_up_questions: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    urgency_rules: Dict[str, float] = Field(default_factory=dict)
    resource_types: List[str] = Field(default_factory=list)
    safety_line_ids: List[str] = Field(default_factory=list)
