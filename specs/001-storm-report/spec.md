# Feature Specification: STORM Wikipedia-Style Report Generation

**Feature Branch**: `001-storm-report`
**Created**: 2026-02-22
**Status**: In Progress
**Input**: Integrate Stanford OVAL's `knowledge-storm` library to generate a comprehensive,
cited Wikipedia-style article from the extracted paper content as an additional pipeline output.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate STORM Article from Analysed Paper (Priority: P1)

A researcher has run `python -m research_analyser analyse paper.pdf` with STORM enabled
and receives a polished, multi-section Wikipedia-style article about the paper's topic,
grounded in the paper's own extracted content (no external web search required).

**Why this priority**: This is the primary deliverable of the feature — an LLM-synthesised
article that contextualises the paper's contribution for readers unfamiliar with the topic.

**Independent Test**: Run `analyse` with `generate_storm_report=True` on a sample PDF;
verify `output/storm_report.md` is created, is non-empty, and contains at least one Markdown
heading derived from the paper title.

**Acceptance Scenarios**:

1. **Given** a fully analysed paper with extracted content,
   **When** `AnalysisOptions(generate_storm_report=True)` is set and `config.storm.enabled=true`,
   **Then** `output/storm_report.md` is written with ≥ 200 words of structured Markdown.

2. **Given** `knowledge-storm` is not installed,
   **When** STORM generation is attempted,
   **Then** the pipeline logs an `ERROR` and continues without crashing; all other outputs are
   still written.

3. **Given** STORM generation raises any exception during the pipeline run,
   **When** the exception is caught by the fail-safe guard in `analyser.py`,
   **Then** `report.storm_report` remains `None`, no `storm_report.md` is written, and the
   returned `AnalysisReport` is otherwise complete.

---

### User Story 2 - Configure STORM via config.yaml (Priority: P2)

A power user tunes STORM's LLM models and conversation depth through `config.yaml` without
touching any Python source code.

**Why this priority**: Supports different cost/quality trade-offs — cheaper models for
experimentation, GPT-4o for production-quality reports.

**Independent Test**: Edit `config.yaml` to set `storm.conv_model: "gpt-4o-mini"` and
`storm.max_conv_turn: 2`; run the pipeline; verify `STORMReporter` is constructed with those
values (inspectable via debug logging).

**Acceptance Scenarios**:

1. **Given** `config.yaml` has `storm.enabled: true` and a custom `conv_model`,
   **When** `Config.load()` is called,
   **Then** `config.storm.conv_model` reflects the YAML value.

2. **Given** `config.yaml` has `storm.enabled: false`,
   **When** `analyse()` is called with `generate_storm_report=True`,
   **Then** the STORM step is skipped and no `storm_report.md` is produced.

---

### User Story 3 - Custom Paper-Content Retrieval (No External API) (Priority: P2)

The STORM pipeline uses only the paper's own extracted sections, equations, and references as
its retrieval corpus — no external API key or internet connection is required for the retrieval
step.

**Why this priority**: Makes the feature usable in air-gapped environments and avoids requiring
additional API keys beyond `OPENAI_API_KEY`.

**Independent Test**: Instantiate `PaperContentRM` with a mock `ExtractedContent`; call
`rm.forward("methodology")` and verify the returned `dspy.Example` objects contain snippets
drawn from the mock content's sections.

**Acceptance Scenarios**:

1. **Given** an `ExtractedContent` with 5 sections,
   **When** `PaperContentRM.forward("results")` is called,
   **Then** the result list contains at most `k` items, each with `url`, `description`, and
   `snippets` attributes.

2. **Given** a query matching no section titles or snippet text,
   **When** `PaperContentRM.forward("unrelated query xyz")` is called,
   **Then** chunks are still returned (lowest-scoring ones) rather than an empty list.

---

### User Story 4 - STORM Report Persisted in save_all (Priority: P3)

When `ReportGenerator.save_all()` is called and `report.storm_report` is set, the STORM
article is written to `output/storm_report.md` alongside the other output files.

**Why this priority**: Ensures the STORM report participates in the standard output directory
convention used by CLI, API, and UI consumers.

**Independent Test**: Call `save_all()` with a mock `AnalysisReport` that has `storm_report`
set to a non-empty string; assert `output/storm_report.md` exists and matches the field value.

**Acceptance Scenarios**:

1. **Given** `report.storm_report = "# Article\n\nContent."`,
   **When** `ReportGenerator.save_all(report, output_dir)` is called,
   **Then** `output_dir/storm_report.md` exists with identical content.

2. **Given** `report.storm_report = None`,
   **When** `save_all()` is called,
   **Then** no `storm_report.md` is created in the output directory.

---

### Edge Cases

- What if the paper title contains special characters that STORM sanitises differently across
  OS/versions? → `_read_storm_output` uses `rglob("*.txt")` as a fallback rather than
  constructing the path from the topic string.
- What if the extracted content has no sections (only an abstract)? → `PaperContentRM` still
  produces at least the abstract chunk; STORM can generate an article from it.
- What if `max_conv_turn=0` or `max_perspective=0` is set? → Validated by `StormConfig`;
  both MUST be ≥ 1.
- What if `openai_api_key` is `None`? → `STORMReporter._build_lm_configs()` passes `None`;
  `LitellmModel` falls through to `OPENAI_API_KEY` env var; if absent, an auth error is raised
  and caught by the fail-safe guard.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate a Wikipedia-style article when `generate_storm_report=True`
  and `config.storm.enabled=true`, using the paper's extracted content as the only retrieval
  source.
- **FR-002**: System MUST expose all STORM tuning parameters (`conv_model`, `outline_model`,
  `article_model`, `max_conv_turn`, `max_perspective`, `search_top_k`, `retrieve_top_k`) via
  `config.yaml` under the `storm:` key.
- **FR-003**: System MUST write `storm_report.md` to the output directory when the STORM step
  succeeds.
- **FR-004**: System MUST skip the STORM step silently (log `ERROR`, continue) on any exception,
  including `ImportError` when `knowledge-storm` is not installed.
- **FR-005**: `PaperContentRM` MUST rank chunks by keyword overlap with the query and return at
  most `k` results per query, deduplicating across multiple queries in a single `forward()` call.
- **FR-006**: `AnalysisReport.storm_report` MUST be `Optional[str]` with a default of `None`;
  the field MUST be serialisable via `dataclasses.asdict()`.
- **FR-007**: `StormConfig.max_conv_turn` and `StormConfig.max_perspective` MUST both be ≥ 1.

### Key Entities

- **`STORMReporter`**: Orchestrates the STORM pipeline; owns `_build_lm_configs()`,
  `generate()`, and `_read_storm_output()`.
- **`PaperContentRM`**: `dspy.Retrieve` subclass; chunks paper content and serves it to STORM.
- **`StormConfig`**: Pydantic `BaseModel` added to `Config`; all fields have safe defaults.
- **`AnalysisReport.storm_report`**: `Optional[str]` field added to the existing dataclass.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pytest tests/test_storm_reporter.py` passes with ≥ 5 unit tests covering
  `PaperContentRM.forward()` and `STORMReporter` error handling.
- **SC-002**: Running the full pipeline with `generate_storm_report=True` on a sample arXiv
  paper produces a `storm_report.md` of ≥ 500 words within the normal pipeline timeout.
- **SC-003**: Setting `storm.enabled: false` in `config.yaml` results in zero additional
  latency (STORM step is skipped entirely).
- **SC-004**: The pipeline completes successfully (exit 0) even when `knowledge-storm` is not
  installed, with a single `ERROR`-level log line.
