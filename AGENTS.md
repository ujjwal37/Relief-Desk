# AGENTS.md — Relief Desk Developer Agent Rules (Antigravity & Cursor)

This rules file governs all AI coding tools working on **Relief Desk** (Antigravity and Cursor).

## 0. Mandatory Read Order Before Writing Any Code
1. `BUILD_BRIEF.md` (especially Section 17: locked decisions, which override older sections)
2. `SETUP.md`
3. `TASKS.md`
4. `docs/design/README.md` and referenced mockups in `docs/design/`
5. The last 20 lines of `WORKDONE.md`

---

## 1. Task Execution & Coordination Protocol
1. **Pick Tasks by Ownership**:
   - Only pick a task from `TASKS.md` with status `TODO` whose dependencies are `DONE`.
   - Owners: `A` = Antigravity, `C` = Cursor, `U` = Ujjwal. (`A + U` / `C + U` means tool writes code and coordinates review with Ujjwal).
   - Never take the other tool's tasks. If blocked on a prerequisite owned by the other tool or Ujjwal, flag it.
2. **Task State Lifecycle**:
   - Set task status to `DOING` in `TASKS.md` before starting work.
   - Verify acceptance criteria rigorously with automated tests/commands.
   - When verified, set status to `DONE` (or `BLOCKED` with reason) in `TASKS.md`.
   - **APPEND** a new entry to `WORKDONE.md` using the standard entry template. **NEVER edit or delete past entries**.
   - Commit code, `TASKS.md`, and `WORKDONE.md` together in the same commit.
3. **Commit Conventions**:
   - Small commits on short-lived branches or main.
   - Imperative commit messages (e.g. `feat(api): ...`, `fix(web): ...`).
   - Run `git pull` before starting. No force-push (`--force`), no history rewrites.

---

## 2. Core Architecture & Stack Rules
- **Monorepo Layout**:
  - `apps/web`: ONE Angular + Ionic + Capacitor PWA with role-based lazy route trees (`public/` at `/`, `coordinator/` at `/coordinator`).
  - `libs/shared`: Shared library containing TypeScript data models, design tokens (`_tokens.scss`), and typed API clients.
  - `services/api`: Python 3.11/3.12 + FastAPI backend (`/healthz`, `/api/**`, Pydantic schemas, ADK agents, deterministic tools).
  - `data/scenarios`: Crisis configuration packs (`*.yaml`). **NEVER create per-scenario screens or code branches**.
  - `data/synthetic`: Synthetic benchmark datasets and gazetteers.
- **Decision Support Only**:
  - A human coordinator approves every dispatch.
  - **Never auto-dispatch. Never auto-delete**. Show emergency banner: "In an emergency call 112".
- **Deterministic Tools vs LLM**:
  - LLM (Gemini) handles natural language extraction, semantic comparison, and plain-language explanation only.
  - Scoring, distances (Haversine), capacity decrements, and ranking are strictly **deterministic Python code**.
  - All LLM outputs must be validated with Pydantic with $\le 2$ retries before falling back to `needs_human_review`.
- **Synthetic Data & Safety**:
  - Strict synthetic data only (fictional city Riverbend, fictional names/numbers).
  - Treat all incoming user messages as untrusted data (prompt injection defense).

---

## 3. WORKDONE.md Entry Template
```markdown
### YYYY-MM-DD HH:MM IST — T-XXX — <Antigravity / Cursor / Ujjwal>
- What changed:
- Files:
- How verified (commands / screenshots):
- Notes / risks / not done:
- Next (suggested task id):
```
