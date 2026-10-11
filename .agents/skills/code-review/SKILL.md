---
name: code-review
description: Comprehensive guidelines for peer reviewing code changes across Angular and FastAPI to ensure adherence to clean architecture, modularity, try-catch safety, and typing.
---

# Code Review Guidelines

Reviewers must inspect both frontend and backend contributions using this checklist:

## 1. Angular Code Review Checklist
- [ ] **Standalone Architecture**: Components, directives, and pipes must be `standalone: true`.
- [ ] **State & Reactivity**: Uses `signal()`, `computed()`, `input()`, `output()` instead of legacy `@Input()` / `@Output()`.
- [ ] **Change Detection**: Uses `ChangeDetectionStrategy.OnPush`.
- [ ] **Separation of Files**: Four distinct files (`.ts`, `.html`, `.less`, `.spec.ts`).
- [ ] **Styling**: Scoped `.less` styles using modular variables; no inline CSS styles or unstyled raw HTML.
- [ ] **API Service Layer**: HTTP calls encapsulated within typed service files; components do not invoke `HttpClient` directly.
- [ ] **Reusability**: Components are modular, parameterized, and located in shared/UI directories when applicable.

## 2. FastAPI Code Review Checklist
- [ ] **Layered Separation**: Controller -> Business Logic (BL) -> Data Access Object (DAO).
- [ ] **Dependency Inversion**: Controller depends on BL; BL depends on DAO. No backwards imports.
- [ ] **Schemas & Typing**: Strict Pydantic models for incoming requests and outgoing responses (`response_model` configured).
- [ ] **Error Handling**: Every layer wraps critical blocks in try-catch/try-except with targeted exception handling and proper status code translation.
- [ ] **Logging**: Every layer logs using `get_logger(__name__)` with informative debug/info/warning/exception logs (no `print()` statements).
- [ ] **Configuration**: Centralized in `app/core/config.py` using `pydantic-settings`.

## 3. Testing Checklist
- [ ] Unit tests exist for both frontend components/services and backend BL/DAO/controllers.
- [ ] Edge cases (empty payload, invalid ID, error conditions) are covered.
