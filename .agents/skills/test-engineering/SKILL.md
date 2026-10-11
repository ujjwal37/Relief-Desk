---
name: test-engineering
description: Guidelines and patterns for writing automated unit and integration tests for Angular (Jasmine/Karma/Vitest) and FastAPI (pytest, TestClient).
---

# Test Engineering Guidelines

## 1. Frontend (Angular) Tests
- Tests reside in `<name>.component.spec.ts` or `<name>.service.spec.ts`.
- Component tests should verify:
  - Component instantiation and signal inputs/outputs.
  - Template rendering based on signal state.
  - User interactions (click, form input submit) and emitted events.
  - Service mocking (`jasmine.createSpyObj` or testing harness).
- Service tests should verify:
  - `HttpClientTestingModule` / `provideHttpClientTesting()` requests.
  - Handling of successful API data and HTTP error status codes.

## 2. Backend (FastAPI) Tests
- Tests reside in `tests/` directory with `pytest`.
- Use `fastapi.testclient.TestClient` for controller / API endpoint integration tests.
- Unit tests for BL layer using isolated mock DAOs or in-memory fixtures.
- Unit tests for DAO layer verifying data persistence and exception handling.
- Verify:
  - Valid request 200/201 response schemas and status codes.
  - Validation failures return 422 / 400.
  - Not found scenarios return 404.
  - Proper logging and exception handling under simulated DAO failures.
