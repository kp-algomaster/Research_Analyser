# Implementation Plan: STORM Wikipedia-Style Report Generation

**Branch**: `001-storm-report` | **Date**: 2026-02-22 | **Spec**: `specs/001-storm-report/spec.md`
**Input**: Feature specification from `specs/001-storm-report/spec.md`

## Summary

Integrate Stanford OVAL's `knowledge-storm` library as an optional pipeline stage that generates
a Wikipedia-style cited article from the paper's own extracted content. The `PaperContentRM`
class replaces external web search with a keyword-ranked in-memory retrieval over the paper's
sections, equations, and references. The `STORMReporter` orchestrates the four-stage STORM
pipeline (research → outline → article → polish) inside a `TemporaryDirectory` and returns
the polished article as a string. The feature is opt-in via `AnalysisOptions.generate_storm_report`
and `config.storm.enabled`; failures are absorbed by the existing fail-safe pattern.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `knowledge-storm>=1.0.0` (includes `dspy-ai`), `pydantic>=2.0`
**Storage**: Temporary directory for STORM intermediate files; final output in `./output/`
**Testing**: `pytest` + `pytest-asyncio`; mock `ExtractedContent` fixtures
**Target Platform**: macOS / Linux server (local GPU optional; LLM calls via OpenAI API)
**Project Type**: library + CLI + web-service
**Performance Goals**: STORM generation completes within the 600 s pipeline timeout; target
  < 120 s for `max_conv_turn=3`, `max_perspective=3` with GPT-4o-mini + GPT-4o
**Constraints**: MUST NOT increase cold-start time when STORM is disabled; `knowledge-storm`
  import is deferred until `STORMReporter.generate()` is called

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Pipeline-First | ✅ | Stage added to `analyser.py` step 9; wired through `AnalysisOptions` |
| II. Async-By-Default | ⚠ | `STORMWikiRunner.run()` is synchronous (blocking); wrapped in `asyncio.to_thread` in Phase 2 |
| III. Fail-Safe | ✅ | `try/except Exception` guard in `analyser.py` step 9; `ImportError` also caught |
| IV. Typed Contracts | ✅ | `storm_report: Optional[str]` added to `AnalysisReport`; `StormConfig` in `config.py` |
| V. Spec-Driven | ✅ | This spec + plan + tasks precede further implementation |

**Async violation mitigation (Principle II)**: `STORMWikiRunner.run()` makes synchronous LLM
calls internally (DSPy's default). Task T007 wraps the blocking call in
`await asyncio.to_thread(runner.run, ...)` to avoid blocking the event loop.

## Project Structure

### Documentation (this feature)

```text
specs/001-storm-report/
├── spec.md          ✅ created
├── plan.md          ✅ this file
└── tasks.md         ← Phase 2 output (/speckit.tasks)
```

### Source Code

```text
research_analyser/
├── storm_reporter.py          ← NEW  (PaperContentRM + STORMReporter)
├── models.py                  ← MODIFIED (AnalysisOptions + AnalysisReport)
├── config.py                  ← MODIFIED (StormConfig)
├── analyser.py                ← MODIFIED (step 9 + STORMReporter init)
└── report_generator.py        ← MODIFIED (save_all storm_report.md)

config.yaml                    ← MODIFIED (storm: section)
requirements.txt               ← MODIFIED (knowledge-storm>=1.0.0)

tests/
├── test_storm_reporter.py     ← NEW
└── fixtures/
    └── sample_content.py      ← NEW (shared ExtractedContent factory)
```

## Phase 0: Research (complete)

Key findings from codebase analysis:

1. **STORM retrieval contract** — `STORMWikiRunner` accepts any callable with a `forward(query)`
   method that returns `list[dspy.Example(url, description, snippets)]`. No need to subclass a
   specific base beyond `dspy.Retrieve(k=...)`.

2. **STORM output location** — Files land in `{output_dir}/{sanitised_topic}/`. Topic
   sanitisation varies by STORM version; `rglob("storm_gen_article_polished.txt")` is more
   robust than path construction.

3. **Blocking LLM calls** — DSPy's `LitellmModel` makes synchronous HTTP requests. The entire
   `runner.run()` call MUST be wrapped with `asyncio.to_thread` to comply with Principle II.

4. **Deferred import pattern** — `_build_paper_rm_class()` factory defers `import dspy` so
   the module is importable without `knowledge-storm` installed. `STORMReporter._check_imports()`
   provides a clear `ImportError` message.

5. **`AnalysisReport` is a `@dataclass`** — Adding `storm_report: Optional[str] = None` as a
   field with a default is backward-compatible (`dataclasses.asdict` serialises it as `None`).

## Phase 1: Design (complete — implemented in this iteration)

All design decisions recorded in this plan; implementation is in progress.

### Data Model Changes

```python
# models.py — AnalysisOptions (new field)
generate_storm_report: bool = False

# models.py — AnalysisReport (new field, default None)
storm_report: Optional[str] = None

# config.py — new StormConfig BaseModel
class StormConfig(BaseModel):
    enabled: bool = False
    conv_model: str = "gpt-4o-mini"
    outline_model: str = "gpt-4o"
    article_model: str = "gpt-4o"
    max_conv_turn: int = 3
    max_perspective: int = 3
    search_top_k: int = 5
    retrieve_top_k: int = 5
```

### STORMReporter Interface

```python
class STORMReporter:
    def __init__(self, openai_api_key, conv_model, outline_model, article_model,
                 max_conv_turn, max_perspective, search_top_k, retrieve_top_k): ...

    def generate(self, report: AnalysisReport) -> str:
        """Blocking call — must be wrapped in asyncio.to_thread by the caller."""
```

### PaperContentRM Interface

```python
class PaperContentRM(dspy.Retrieve):
    def __init__(self, content: ExtractedContent, k: int = 5): ...
    def forward(self, query_or_queries, exclude_urls=None) -> list[dspy.Example]: ...
```

### analyser.py Integration Point

```python
# Step 9 — after save_all, before TTS
if options.generate_storm_report and self.config.storm.enabled:
    try:
        report.storm_report = await asyncio.to_thread(
            self.storm_reporter.generate, report
        )
        if report.storm_report:
            (output_dir / "storm_report.md").write_text(report.storm_report, encoding="utf-8")
    except Exception as exc:
        logger.error(f"STORM report generation failed: {exc}")
```

## Phase 2: Implementation Tasks

See `specs/001-storm-report/tasks.md`.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|------------|--------------------------------------|
| Deferred `dspy` import via factory function | Avoids import-time crash when `knowledge-storm` not installed | Module-level `try/except ImportError` would shadow real errors; conditional class definition at module level is cleaner as a factory |
| `rglob` for STORM output discovery | STORM sanitises topic names inconsistently across versions | Constructing path from topic string breaks with special chars or version changes |
| Synchronous `runner.run()` wrapped in `asyncio.to_thread` | DSPy LLM calls are blocking | Rewriting DSPy to be async is out of scope; `to_thread` is the standard pattern |
