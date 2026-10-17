from fastapi import APIRouter, Depends

from app.agents.sitrep import SitrepResponse, generate_sitrep_fast
from app.api.auth import CoordinatorUser, get_current_coordinator

router = APIRouter(prefix="/api", tags=["Sitrep"])


@router.post("/sitrep", response_model=SitrepResponse)
def create_sitrep(_coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    """One-click situation brief. Drafts only; nothing is sent."""
    return generate_sitrep_fast()
