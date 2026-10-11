"""
Validation script for Relief Desk Synthetic Seeds (T-009).
Ensures data/synthetic/flood_v1/seeds.yaml matches the required schema:
- City metadata with bounding box and coordinates
- 12 wards with bilingual names and bounding coordinates
- ~60 landmarks with Hindi & Latin aliases mapped to valid wards
- 40 ground-truth flood incident seeds with valid types, urgency bands, and coordinates
"""
import sys
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class CityModel(BaseModel):
    name: str = Field(..., min_length=2)
    state: str
    center: Dict[str, float]
    bbox: Dict[str, float]

    @field_validator("center")
    @classmethod
    def validate_center(cls, v):
        if "lat" not in v or "lng" not in v:
            raise ValueError("City center must contain 'lat' and 'lng'")
        return v

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v):
        for k in ["min_lat", "max_lat", "min_lng", "max_lng"]:
            if k not in v:
                raise ValueError(f"Bbox missing {k}")
        if v["min_lat"] >= v["max_lat"] or v["min_lng"] >= v["max_lng"]:
            raise ValueError("Invalid bbox coordinates")
        return v

class WardModel(BaseModel):
    id: str = Field(..., pattern=r"^ward_\d{1,2}$")
    number: int = Field(..., ge=1, le=20)
    name_en: str
    name_hi: str

class LandmarkModel(BaseModel):
    id: str = Field(..., pattern=r"^LM-\d{2,3}$")
    name: str
    ward_id: str
    lat: float
    lng: float
    category: Literal[
        "school", "hospital", "temple", "mosque", "market", 
        "metro_station", "bridge", "ghat", "shelter", 
        "police_station", "community_hall"
    ]
    aliases_hi: List[str] = Field(..., min_length=1)
    aliases_en: List[str] = Field(..., min_length=1)

class VulnerableFlagsModel(BaseModel):
    child: bool = False
    elderly: bool = False
    disabled: bool = False
    pregnant: bool = False
    medical_need: bool = False

class IncidentSeedModel(BaseModel):
    id: str = Field(..., pattern=r"^INC-\d{3}$")
    type: Literal["rescue", "food", "medical", "shelter", "info", "other"]
    ward_id: str
    landmark_id: str
    lat: float
    lng: float
    people: int = Field(..., ge=1, le=500)
    vulnerable: VulnerableFlagsModel
    hazard: Literal["water_rising", "stranded", "injury", "none", "unknown"]
    urgency_band: Literal["critical", "high", "medium", "low"]
    reported_at: str
    description: str
    sample_reports: List[Dict[str, str]] = Field(..., min_length=1)

class SeedsDatasetModel(BaseModel):
    version: str
    scenario_pack: str
    city: CityModel
    wards: List[WardModel] = Field(..., min_length=12, max_length=12)
    landmarks: List[LandmarkModel] = Field(..., min_length=50)
    incidents: List[IncidentSeedModel] = Field(..., min_length=40, max_length=40)

    @model_validator(mode="after")
    def cross_validate(self):
        ward_ids = {w.id for w in self.wards}
        landmark_ids = {lm.id for lm in self.landmarks}

        # Validate landmarks refer to valid wards
        for lm in self.landmarks:
            if lm.ward_id not in ward_ids:
                raise ValueError(f"Landmark {lm.id} references non-existent ward {lm.ward_id}")

        # Validate incidents refer to valid wards and landmarks
        for inc in self.incidents:
            if inc.ward_id not in ward_ids:
                raise ValueError(f"Incident {inc.id} references non-existent ward {inc.ward_id}")
            if inc.landmark_id not in landmark_ids:
                raise ValueError(f"Incident {inc.id} references non-existent landmark {inc.landmark_id}")
        return self

def validate_yaml(yaml_path: Path) -> SeedsDatasetModel:
    if not yaml_path.exists():
        raise FileNotFoundError(f"File not found: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    dataset = SeedsDatasetModel.model_validate(data)
    return dataset

if __name__ == "__main__":
    target = Path("data/synthetic/flood_v1/seeds.yaml")
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    try:
        dataset = validate_yaml(target)
        print("SUCCESS: Seeds dataset is valid!")
        print(f"City: {dataset.city.name} ({dataset.city.state})")
        print(f"Total Wards: {len(dataset.wards)}")
        print(f"Total Landmarks: {len(dataset.landmarks)}")
        print(f"Total Incidents: {len(dataset.incidents)}")
        sys.exit(0)
    except Exception as e:
        print(f"VALIDATION ERROR: {e}", file=sys.stderr)
        sys.exit(1)
