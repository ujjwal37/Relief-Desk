# Relief Desk Architecture & Engineering Guidelines

## Overview
Relief Desk is a crisis & disaster response coordination platform.
The architecture consists of:
1. **Frontend**: Angular (Standalone components, Signals, `.less` styling, `.html` templates, `.ts` logic, typed API services).
2. **Backend**: FastAPI (Clean 3-tier architecture: Controller -> Business Logic (BL) -> Data Access Object (DAO), Pydantic schemas, unified config, structured logging, try-catch safety).

## Orchestration Workflow
1. **Story Brief**: Define what needs to be implemented, sub-tasks, frontend requirements, and backend requirements.
2. **Frontend Plan & Backend Plan**: Comprehensive technical plans based on the story brief.
3. **Parallel Subagents**:
   - `frontend-engineer`: Implements Angular reusable components, services, and views.
   - `backend-engineer`: Implements FastAPI Controller, BL, DAO, Schemas, and integration points.
4. **Code Review Agent**: Validates standards, type safety, modular boundaries, error handling, and styling.
5. **Test Engineering**: Writes automated tests for frontend and backend.

## Technical Rules
### Frontend Rules (Angular)
- Standalone components only (`standalone: true`).
- Signal-first reactivity: `input()`, `output()`, `signal()`, `computed()`.
- Explicit OnPush change detection: `changeDetection: ChangeDetectionStrategy.OnPush`.
- 4-file component convention (`.ts`, `.html`, `.less`, `.spec.ts`).
- Centralized reusable UI components in `src/app/shared/components/`.
- Services for API calls with typed interfaces and error handling.

### Backend Rules (FastAPI)
- Modular 3-tier structure:
  - `controller`: API endpoints, request validation, response serialization, HTTP status codes.
  - `bl`: Business logic and workflows, domain validations.
  - `dao`: Data persistence, storage queries, DB abstraction.
- Single configuration file: `app/core/config.py`.
- Centralized logging: `app/core/logger.py` with `get_logger(__name__)`.
- Every critical block must include try-catch / try-except with appropriate logging.
- Pydantic models for all input requests and output responses.
