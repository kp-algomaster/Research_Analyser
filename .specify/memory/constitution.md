<!-- Sync Impact Report
  Version change: 1.0.0 → 1.1.0
  Modified principles: none renamed
  Added sections: VI. Ship-and-Verify (new principle)
  Removed sections: none
  Templates updated:
    ✅ .specify/memory/constitution.md (this file)
  Follow-up TODOs: update tasks.md to mark T022-T026 as constitution-driven
-->

# Research Analyser Constitution

## Core Principles

### I. Pipeline-First Architecture

Every new capability MUST be expressed as a stage in the unified `ResearchAnalyser.analyse()`
pipeline, not as an ad-hoc script or one-off utility. Modules are wired through `analyser.py`;
direct cross-module imports between pipeline stages are forbidden. Pipeline stages communicate
exclusively through the data models defined in `models.py`.

**Rationale**: Ensures the pipeline remains the single entry-point for all analysis — CLI, API,
and UI all call the same `analyse()` path, guaranteeing consistent behaviour.

### II. Async-By-Default I/O

All network and disk I/O MUST use `async`/`await`. Blocking calls inside `async` functions are
forbidden without wrapping in `asyncio.to_thread`. Pipeline stages that can run concurrently
MUST be dispatched via `asyncio.gather`.

**Rationale**: OCR, diagram generation, review, and STORM are independently long-running;
sequential execution wastes wall-clock time.

### III. Fail-Safe Optional Components

Non-critical pipeline stages (diagrams, review, STORM report, audio narration) MUST NOT raise
exceptions that abort the pipeline. They MUST be guarded by `try/except` with `ERROR`-level
structured logging. `AnalysisOptions` boolean flags control opt-in; expensive/slow features
default to `False`.

**Rationale**: A partial result is far more valuable than a hard failure when OCR succeeds but
an optional AI step fails.

### IV. Typed Data Contracts

Every inter-module data structure MUST be declared as a `@dataclass` in
`research_analyser/models.py`. No ad-hoc dicts or TypedDicts may cross module boundaries.
Adding a field is a MINOR change; removing or renaming is MAJOR and requires updating all
callers before merging.

**Rationale**: `models.py` is the project's schema registry; changes there are the canonical
signal for breaking changes across the pipeline.

### VI. Ship-and-Verify

Once a feature's task list reaches 100% completion AND the full test suite passes (`pytest tests/`
with zero failures), the implementation MUST be committed and pushed to the remote repository
before any new feature work begins. The commit MUST:

1. Reference the spec branch (e.g., `feat(001-storm-report): ...`).
2. Include only files related to the completed feature (no unrelated changes).
3. Be preceded by a final `pytest tests/` and `ruff check .` run — both MUST be clean.
4. Mark all tasks `[x]` in `specs/<###-feature>/tasks.md` before the push.

**Rationale**: Prevents "local only" completed features from diverging from the remote. A push
is the signal that the feature is done, reviewable, and safe to build on.

### V. Spec-Driven Development

New features MUST begin with `specs/<###-feature-name>/spec.md` before any implementation code
is written. The spec-kit workflow (`spec → plan → tasks → implement`) MUST be followed.
The root `SPEC.md` serves as the overarching system specification and MUST stay in sync with
implemented interfaces after each feature lands.

**Rationale**: Prevents scope creep, ensures testability is designed upfront, and creates an
auditable record of design decisions.

## Technology Stack

- **Language**: Python 3.11+
- **Package manager**: `uv` (lock-file driven)
- **Core frameworks**: Pydantic v2, LangGraph, DSPy + `knowledge-storm`, FastAPI, Streamlit
- **OCR**: MonkeyOCR 1.5 (`MonkeyOCR-pro-3B`)
- **Diagram generation**: PaperBanana (Gemini free tier default)
- **Testing**: `pytest` + `pytest-asyncio`; fixtures in `tests/fixtures/`
- **Linting / types**: `ruff`, `mypy`
- **Config**: `config.yaml` + env-var overrides via `pydantic-settings`; secrets NEVER committed

## Development Workflow

1. Create `specs/<###-feature>/spec.md` using `/speckit.specify`.
2. Run `/speckit.plan` → `plan.md`; run `/speckit.tasks` → `tasks.md`.
3. Write failing tests before implementation code (TDD encouraged, not mandated for trivial
   changes).
4. Run `/speckit.implement` task-by-task; mark tasks `[x]` as you go.
5. Quality gates: `pytest tests/` MUST pass; `ruff check .` MUST report zero errors.
6. Sync `SPEC.md` at repo root if public interfaces changed.
7. Commit convention: `feat:` / `fix:` / `docs:` / `refactor:` / `test:` prefixes; reference
   spec branch in message.

## Governance

This constitution supersedes all implicit conventions. Amendments MUST:

1. Increment the version below and update `LAST_AMENDED_DATE`.
2. Be reflected in any affected `specs/*/plan.md` and `specs/*/tasks.md`.
3. Include a "Constitution Change" label in the PR description.

Versioning policy:
- **MAJOR** (`X.0.0`): Removal or redefinition of a Core Principle.
- **MINOR** (`X.Y.0`): Addition of a new principle or material guidance expansion.
- **PATCH** (`X.Y.Z`): Clarifications, wording, or non-semantic refinements.

All PRs MUST include a one-line constitution compliance note in the description
(e.g., "Complies: II (async I/O), III (fail-safe), IV (models.py contract)").

Runtime AI-assistant guidance: see `CLAUDE.md`.

**Version**: 1.1.0 | **Ratified**: 2026-02-22 | **Last Amended**: 2026-02-22
