---
name: fastapi-clean-architecture
description: Best practices for building modular FastAPI backends using Controller -> BL -> DAO layers, Pydantic response models, unified config, structured logging, and try-catch error handling.
---

# FastAPI 3-Tier Modular Architecture Guide

This skill specifies the clean layered architecture for building resilient, maintainable FastAPI backends.

## 1. Architectural Layers & Responsibilities

The codebase follows the strict separation:
`Controller (Router) -> Business Logic (BL) -> Data Access Object (DAO)`

### Layer Responsibilities:
1. **Controller Layer (`app/api/` or `app/modules/<module>/controller.py`)**:
   - Handles HTTP requests, path/query params, and request bodies.
   - Validates inputs via Pydantic schemas.
   - Injects Business Logic (BL) dependencies.
   - Returns typed Pydantic responses.
   - Catches unhandled domain exceptions and maps them to appropriate HTTP status codes (`HTTPException`).
   - Logs request-level events with context.

2. **Business Logic Layer (`app/modules/<module>/bl.py`)**:
   - Implements domain rules, calculations, workflows, and state transitions.
   - Interacts with DAO instances for persistence.
   - Completely agnostic of HTTP/FastAPI (no `Request` or `HTTPException` dependencies).
   - Raises domain-specific exceptions (e.g. `EntityNotFoundError`, `ValidationError`).
   - Uses try-except blocks around critical operations with informative logging.

3. **Data Access Object Layer (`app/modules/<module>/dao.py`)**:
   - Executes database queries, ORM/SQL operations, or data storage interactions.
   - Never contains business validation logic.
   - Catches database connection/query exceptions, logs them with error details, and re-raises domain persistence errors.

4. **Schemas Layer (`app/modules/<module>/schemas.py`)**:
   - Defines Pydantic models for incoming requests (`CreateRequest`, `UpdateRequest`) and outgoing responses (`ResponseModel`, `ListResponse`).
   - Strict typing, field descriptions, and examples.

5. **Configuration Layer (`app/core/config.py`)**:
   - Single unified configuration using `pydantic-settings` (`BaseSettings`).
   - Reads environment variables with defaults.

6. **Logging Layer (`app/core/logger.py`)**:
   - Configures unified Python standard logger with timestamp, level, module, and message format.
   - Every module imports and uses `logger = get_logger(__name__)`.

---

## 2. Standard Implementation Template

### A. Core Config (`app/core/config.py`)
```python
import logging
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Relief Desk API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite:///./relief_desk.db"
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

### B. Core Logger (`app/core/logger.py`)
```python
import logging
import sys
from app.core.config import settings

def setup_logging():
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

### C. Schemas (`app/modules/relief_requests/schemas.py`)
```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ReliefRequestBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    category: str = Field(..., description="E.g., Medical, Food, Shelter")
    urgency: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    description: str = Field(..., max_length=1000)
    contact_name: str
    contact_phone: str
    location: str

class ReliefRequestCreate(ReliefRequestBase):
    pass

class ReliefRequestResponse(ReliefRequestBase):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

### D. DAO Layer (`app/modules/relief_requests/dao.py`)
```python
from app.core.logger import get_logger
from app.modules.relief_requests.schemas import ReliefRequestCreate

logger = get_logger(__name__)

class ReliefRequestDAO:
    def __init__(self):
        # Database session or storage reference
        self._storage: dict[str, dict] = {}

    def create(self, record_id: str, data: ReliefRequestCreate, timestamp) -> dict:
        try:
            logger.info("DAO: Inserting relief request with ID %s", record_id)
            entity = {
                "id": record_id,
                **data.model_dump(),
                "status": "OPEN",
                "created_at": timestamp,
                "updated_at": timestamp
            }
            self._storage[record_id] = entity
            logger.info("DAO: Successfully inserted record %s", record_id)
            return entity
        except Exception as e:
            logger.exception("DAO: Error inserting relief request %s: %s", record_id, str(e))
            raise

    def get_by_id(self, record_id: str) -> dict | None:
        try:
            logger.info("DAO: Querying relief request with ID %s", record_id)
            return self._storage.get(record_id)
        except Exception as e:
            logger.exception("DAO: Error querying relief request %s: %s", record_id, str(e))
            raise

    def list_all(self) -> list[dict]:
        try:
            logger.info("DAO: Fetching all relief requests")
            return list(self._storage.values())
        except Exception as e:
            logger.exception("DAO: Error fetching relief requests: %s", str(e))
            raise
```

### E. Business Logic (BL) Layer (`app/modules/relief_requests/bl.py`)
```python
import uuid
from datetime import datetime, timezone
from app.core.logger import get_logger
from app.modules.relief_requests.dao import ReliefRequestDAO
from app.modules.relief_requests.schemas import ReliefRequestCreate

logger = get_logger(__name__)

class ReliefRequestBL:
    def __init__(self, dao: ReliefRequestDAO | None = None):
        self.dao = dao or ReliefRequestDAO()

    def create_request(self, payload: ReliefRequestCreate) -> dict:
        try:
            logger.info("BL: Processing creation of relief request for %s", payload.contact_name)
            record_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            created = self.dao.create(record_id, payload, now)
            logger.info("BL: Successfully created relief request ID %s", record_id)
            return created
        except Exception as e:
            logger.exception("BL: Failed to process relief request creation: %s", str(e))
            raise

    def get_request(self, record_id: str) -> dict:
        try:
            logger.info("BL: Retrieving relief request ID %s", record_id)
            record = self.dao.get_by_id(record_id)
            if not record:
                logger.warning("BL: Relief request ID %s not found", record_id)
                raise ValueError(f"Relief request {record_id} not found")
            return record
        except Exception as e:
            logger.exception("BL: Failed to retrieve relief request %s: %s", record_id, str(e))
            raise

    def list_requests(self) -> list[dict]:
        try:
            logger.info("BL: Listing relief requests")
            return self.dao.list_all()
        except Exception as e:
            logger.exception("BL: Failed to list relief requests: %s", str(e))
            raise
```

### F. Controller Layer (`app/modules/relief_requests/controller.py`)
```python
from fastapi import APIRouter, HTTPException, status, Depends
from app.core.logger import get_logger
from app.modules.relief_requests.schemas import ReliefRequestCreate, ReliefRequestResponse
from app.modules.relief_requests.bl import ReliefRequestBL

logger = get_logger(__name__)
router = APIRouter(prefix="/relief-requests", tags=["Relief Requests"])

def get_relief_bl() -> ReliefRequestBL:
    return ReliefRequestBL()

@router.post("/", response_model=ReliefRequestResponse, status_code=status.HTTP_201_CREATED)
def create_relief_request(
    payload: ReliefRequestCreate,
    bl: ReliefRequestBL = Depends(get_relief_bl)
):
    try:
        logger.info("Controller: Received request to create relief request")
        result = bl.create_request(payload)
        return result
    except ValueError as ve:
        logger.warning("Controller: Validation error: %s", str(ve))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception("Controller: Unexpected error creating relief request: %s", str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.get("/", response_model=list[ReliefRequestResponse])
def get_all_relief_requests(bl: ReliefRequestBL = Depends(get_relief_bl)):
    try:
        logger.info("Controller: Fetching all relief requests")
        return bl.list_requests()
    except Exception as e:
        logger.exception("Controller: Error fetching relief requests: %s", str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
```
