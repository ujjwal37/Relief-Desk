from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import DEMO_COORDINATOR_EMAIL, CoordinatorUser, get_current_coordinator
from app.config import settings
from app.tools.storage import storage_service

router = APIRouter(prefix="/api", tags=["Demo"])


@router.post("/demo/reset")
def reset_demo(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    """Reload synthetic seeds into the running API.

    Allowed in demo mode, or for the synthetic demo coordinator account even when DEMO_MODE is off,
    so a judge can undo merges and dispatches between runs. Real coordinators get 403.
    """
    if not settings.DEMO_MODE and (coordinator.email or "").lower() != DEMO_COORDINATOR_EMAIL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo reset is only available in demo mode or for the demo coordinator")
    summary = storage_service.reset_demo()
    summary["actor"] = coordinator.email
    return summary
