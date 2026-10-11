from typing import List
from fastapi import APIRouter, HTTPException, status
from app.models.scenario import ScenarioConfig
from app.tools.scenario_loader import scenario_registry

router = APIRouter(prefix="/api/scenarios", tags=["Scenarios"])


@router.get("", response_model=List[ScenarioConfig])
def list_scenarios():
    return scenario_registry.list_scenarios()


@router.get("/{scenario_id}", response_model=ScenarioConfig)
def get_scenario(scenario_id: str):
    scenario = scenario_registry.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario pack '{scenario_id}' not found"
        )
    return scenario
