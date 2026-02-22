---
description: "Task list for STORM Wikipedia-style report generation"
---

# Tasks: STORM Wikipedia-Style Report Generation

**Input**: `specs/001-storm-report/spec.md`, `specs/001-storm-report/plan.md`
**Prerequisites**: spec.md ✅, plan.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story (US1–US4)
- Exact file paths included in each description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and fixtures shared by all stories.

- [x] T001 [P] Add `knowledge-storm>=1.0.0` to `requirements.txt`
- [x] T002 [P] Add `StormConfig` BaseModel to `research_analyser/config.py`
- [x] T003 [P] Add `storm: StormConfig` field to `Config` in `research_analyser/config.py`
- [x] T004 [P] Add `storm:` section to `config.yaml` with all defaults and inline comments
- [x] T005 [P] Create `tests/fixtures/` directory and add `tests/fixtures/__init__.py`
- [x] T006 [P] Create `tests/fixtures/sample_content.py` with `make_extracted_content()` factory
  returning a minimal `ExtractedContent` with title, abstract, 3 sections, 2 equations, 2 references

**Checkpoint**: Dependencies declared; test fixtures available.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data model and module skeleton that all stories depend on.

- [x] T007 [P] [All] Add `generate_storm_report: bool = False` to `AnalysisOptions` in
  `research_analyser/models.py`
- [x] T008 [P] [All] Add `storm_report: Optional[str] = None` field to `AnalysisReport` in
  `research_analyser/models.py`
- [x] T009 [US1] Create `research_analyser/storm_reporter.py` with:
  - `_build_chunks(content: ExtractedContent) -> list[dict]` module-level function
  - `_build_paper_rm_class()` factory that defers `import dspy` and returns `PaperContentRM`
  - `PaperContentRM(dspy.Retrieve)` with `__init__(content, k)` and `forward(query_or_queries, exclude_urls)`
  - `STORMReporter.__init__()` accepting all config params
  - `STORMReporter._check_imports()` raising `ImportError` with install instructions
  - `STORMReporter._build_lm_configs()` building `STORMWikiLMConfigs`
  - `STORMReporter.generate(report) -> str` (synchronous — see T011)
  - `_read_storm_output(base: Path) -> str` module-level helper using `rglob`

**Checkpoint**: Core module exists and is importable; models updated.

---

## Phase 3: User Story 1 — Generate STORM Article (Priority: P1) 🎯 MVP

**Goal**: End-to-end generation of `output/storm_report.md` from an analysed paper.

**Independent Test**: `pytest tests/test_storm_reporter.py::test_generate_returns_string` passes
with a mocked `STORMWikiRunner`.

### Tests for User Story 1

> **Write these tests FIRST; ensure they FAIL before implementing T011–T013**

- [x] T010 [P] [US1] `tests/test_storm_reporter.py`:
  - `test_check_imports_raises_when_not_installed` — mock `builtins.__import__` to raise `ModuleNotFoundError` for `knowledge_storm`; assert `ImportError` raised with helpful message
  - `test_generate_returns_string` — patch `STORMWikiRunner` and `_read_storm_output`; assert `generate()` returns the mocked article string
  - `test_generate_returns_empty_on_runner_exception` — patch `STORMWikiRunner.run` to raise; assert `generate()` propagates the exception (fail-safe guard is in `analyser.py`, not here)
  - `test_read_storm_output_finds_polished_first` — create temp dir with both `.txt` files; assert polished variant is returned
  - `test_read_storm_output_falls_back_to_rglob` — create temp dir with only a nested `.txt`; assert it is returned

### Implementation for User Story 1

- [x] T011 [US1] Wrap `runner.run()` call in `STORMReporter.generate()` with
  `asyncio.to_thread` **in `analyser.py` step 9** (the generator itself remains sync;
  the async wrapper lives in the pipeline):

  ```python
  # analyser.py step 9
  if options.generate_storm_report and self.config.storm.enabled:
      try:
          report.storm_report = await asyncio.to_thread(
              self.storm_reporter.generate, report
          )
          if report.storm_report:
              (output_dir / "storm_report.md").write_text(
                  report.storm_report, encoding="utf-8"
              )
      except Exception as exc:
          logger.error(f"STORM report generation failed: {exc}")
  ```

- [x] T012 [US1] Instantiate `STORMReporter` in `ResearchAnalyser.__init__()` in
  `research_analyser/analyser.py` using all `config.storm.*` fields
- [x] T013 [US1] Import `STORMReporter` at top of `research_analyser/analyser.py`

**Checkpoint**: `output/storm_report.md` generated when `generate_storm_report=True` and
`storm.enabled=true`; pipeline does not crash when STORM fails.

---

## Phase 4: User Story 2 — Config-Driven STORM (Priority: P2)

**Goal**: All STORM knobs exposed and tested through `config.yaml`.

**Independent Test**: Load config from YAML fragment; assert `config.storm.*` fields match.

### Tests for User Story 2

- [x] T014 [P] [US2] `tests/test_storm_reporter.py`:
  - `test_storm_config_defaults` — instantiate `StormConfig()`; assert all defaults match spec
  - `test_storm_config_from_yaml` — parse a YAML string with custom values via `Config.load()`
    using a temp config file; assert `config.storm.conv_model` reflects YAML value
  - `test_pipeline_skips_storm_when_disabled` — patch `STORMReporter.generate`; set
    `config.storm.enabled=False`; run `analyse()` with `generate_storm_report=True`; assert
    `generate` was never called

### Implementation for User Story 2

- [x] T015 [P] [US2] `StormConfig` and `Config.storm` field already implemented (T002/T003)
- [x] T016 [P] [US2] `config.yaml` `storm:` section already added (T004)
- [x] T017 [US2] Add `max_conv_turn` and `max_perspective` validators to `StormConfig` using
  `pydantic.field_validator` that raise `ValueError` if value < 1

**Checkpoint**: Config values flow end-to-end; invalid values raise at startup, not mid-run.

---

## Phase 5: User Story 3 — PaperContentRM Unit Tests (Priority: P2)

**Goal**: Verified keyword-ranking retrieval with deduplication.

**Independent Test**: `pytest tests/test_storm_reporter.py -k paper_rm` passes with no mocking
of external services.

### Tests for User Story 3

- [x] T018 [P] [US3] `tests/test_storm_reporter.py`:
  - `test_paper_rm_forward_returns_k_results` — `PaperContentRM(content, k=3).forward("method")`
    returns ≤ 3 items
  - `test_paper_rm_forward_deduplicates_across_queries` — two overlapping queries return
    deduplicated results
  - `test_paper_rm_forward_no_match_still_returns_results` — unrelated query still returns
    chunks (not empty list)
  - `test_paper_rm_chunks_include_abstract` — abstract chunk is present in `rm.chunks`
  - `test_paper_rm_chunks_include_equations` — equation chunk present when content has
    equations with descriptions
  - `test_paper_rm_excludes_urls` — URLs in `exclude_urls` are not returned

### Implementation for User Story 3

- [x] T019 [US3] `PaperContentRM` already implemented in `storm_reporter.py` (T009)

**Checkpoint**: All `test_paper_rm_*` tests pass without any network calls.

---

## Phase 6: User Story 4 — save_all Persistence (Priority: P3)

**Goal**: `ReportGenerator.save_all()` writes `storm_report.md` when field is set.

**Independent Test**: Call `save_all()` with a mock report; assert file presence/absence.

### Tests for User Story 4

- [x] T020 [P] [US4] `tests/test_report_generator.py` (new test file or extend existing):
  - `test_save_all_writes_storm_report` — mock report with `storm_report="# Test"`;
    call `save_all()`; assert `output/storm_report.md` content equals `"# Test"`
  - `test_save_all_skips_storm_report_when_none` — mock report with `storm_report=None`;
    call `save_all()`; assert `output/storm_report.md` does not exist

### Implementation for User Story 4

- [x] T021 [US4] `storm_report.md` persistence block already added to `save_all()` in
  `research_analyser/report_generator.py`

**Checkpoint**: All user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T022 [P] Update `SPEC.md` §3.5 (ReportGenerator) to document `storm_report.md` output
- [x] T023 [P] Update `SPEC.md` §2.2 (AnalysisOptions) and §2.5 (AnalysisReport) with new fields
- [x] T024 [P] Update `SPEC.md` §5 (Configuration Schema) to include `storm:` section
- [x] T025 [P] Update `README.md` "Output Files" table to list `storm_report.md`
- [x] T026 [P] Add `STORM_REPORT` section to `README.md` "Configuration" documenting opt-in flags
- [x] T027 Run `pytest tests/` — all tests MUST pass
- [x] T028 Run `ruff check research_analyser/storm_reporter.py tests/test_storm_reporter.py`
- [x] T029 Add `tests/test_storm_reporter.py` to `tests/` and ensure `pytest` autodiscovers it

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; all tasks parallel
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — blocks Phase 3+
- **Phase 3 (US1)**: Tests (T010) MUST fail before implementing T011–T013
- **Phase 4 (US2)**: Depends on Phase 2; T017 is independent of Phase 3
- **Phase 5 (US3)**: Depends on Phase 2 (needs `PaperContentRM` from T009)
- **Phase 6 (US4)**: Depends on Phase 2; independent of Phases 3/5
- **Phase 7 (Polish)**: Depends on all user stories passing

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models and config before services
- Services before pipeline integration

### Parallel Opportunities

- T005, T006 (fixtures) can run alongside T002–T004
- T014, T018, T020 (tests for US2/3/4) can all start after Phase 2 completes
- T022–T026 (docs) can run in parallel with any phase

### Completed Tasks Summary

Already implemented in this session:

| Task | File | Status |
|------|------|--------|
| T001 | `requirements.txt` | ✅ |
| T002/T003 | `research_analyser/config.py` | ✅ |
| T004 | `config.yaml` | ✅ |
| T007/T008 | `research_analyser/models.py` | ✅ |
| T009 | `research_analyser/storm_reporter.py` | ✅ |
| T011/T012/T013 | `research_analyser/analyser.py` | ✅ (sync; T011 needs async wrap) |
| T015/T016 | config already done | ✅ |
| T019 | `storm_reporter.py` | ✅ |
| T021 | `research_analyser/report_generator.py` | ✅ |

**Remaining work**: T005–T006 (fixtures), T010 (US1 tests), T014 (US2 tests), T017 (validator),
T018 (US3 tests), T020 (US4 tests), T022–T029 (polish + sync SPEC.md).
