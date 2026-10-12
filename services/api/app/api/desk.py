"""Ask the desk. Read-only: a question in, matching cases out. Nothing is written."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.desk_query import ask
from app.api.assist import wards_for
from app.api.auth import CoordinatorUser, get_current_coordinator
from app.tools.storage import storage_service

router = APIRouter(prefix="/api/desk", tags=["Desk"])


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    lang: Optional[str] = None


@router.post("/ask")
def ask_desk(body: AskBody, coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is empty")
    allowed = wards_for(coordinator.email)
    rows = [r for r in storage_service._requests.values() if not allowed or r.ward_id in allowed]
    return ask(question, rows)
