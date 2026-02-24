# Tasks: VS Code Extension — Research Analyser Integration

**Input**: Design documents from `specs/002-vscode-extension/`
**Feature branch**: `002-vscode-extension`
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
**Data model**: [data-model.md](data-model.md) | **Contracts**: [contracts/](contracts/)

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- All paths are relative to `research-analyser-vscode/` (the new extension repo)

---

## Phase 1: Setup (Project Scaffold)

**Purpose**: Create the TypeScript extension repository with build tooling and directory structure.

- [X] T001 Initialise `research-analyser-vscode/` git repository and run `npm init -y`
- [X] T002 Replace generated `package.json` with full extension manifest (name, publisher, engines, main, activationEvents, contributes stubs) per `specs/002-vscode-extension/spec.md §3`
- [X] T003 [P] Create `tsconfig.json` (module: commonjs, target: ES2020, strict: true, outDir: out) per `specs/002-vscode-extension/quickstart.md §4`
- [X] T004 [P] Create `esbuild.config.js` with dual-bundle setup (extension host Node.js + webview browser) per `specs/002-vscode-extension/quickstart.md §5`
- [X] T005 [P] Create `.eslintrc.json` with `@typescript-eslint` recommended rules
- [X] T006 Install all npm dependencies (`@types/vscode`, `typescript`, `esbuild`, `katex`, `@vscode/test-electron`, `mocha`, `sinon`) per `specs/002-vscode-extension/quickstart.md §3`
- [X] T007 Copy KaTeX 0.16 fonts, CSS, and JS from `node_modules/katex/dist/` into `src/webview/katex/` per `specs/002-vscode-extension/quickstart.md §7`
- [X] T008 [P] Create `.vscode/launch.json` (extensionHost debug config) and `.vscode/tasks.json` (preLaunchTask: npm build) per `specs/002-vscode-extension/quickstart.md §9`
- [X] T009 [P] Create full source directory tree: `src/{store,providers,panels,commands,decorators,api,util,webview/katex}` and `tests/{unit,integration}`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared TypeScript types, entry point skeleton, and core singleton that all user-story phases depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T010 Create `src/types/index.ts` with all TypeScript interfaces from `specs/002-vscode-extension/data-model.md`: `AnalysisReport`, `ExtractedContent`, `Section`, `Equation`, `Diagram`, `PaperSummary`, `PeerReview`, `AnalyseOptions`, `AnalyseRequest`, `ProgressEvent`, `EquationRef`, `EquationIndex`, `CodeLocation`, `AnnotationMap`, `InsertFormat`, `ReportStoreState`, `ToWebviewMessage`, `FromWebviewMessage`
- [X] T011 Create `src/store/ReportStore.ts` — singleton holding `ReportStoreState` (discriminated union: `empty | loading | loaded | error`), `EventEmitter` for `onDidChange`, `load(report)`, `clear()`, `getEquationIndex()` per `specs/002-vscode-extension/data-model.md §ReportStore`
- [X] T012 [P] Create `src/extension.ts` — `activate()` / `deactivate()` skeleton: instantiate `ReportStore`, register all commands (stub disposables), set up `researchAnalyser.serverRunning` context key, push all disposables to `context.subscriptions`
- [X] T013 [P] Create `src/util/symbolIndex.ts` — `buildSymbolIndex(equations: Equation[]): EquationIndex` using regex-based extraction from `specs/002-vscode-extension/research.md R-04`: Greek letters `\\([a-zA-Z]+)`, subscript identifiers `[a-zA-Z][a-zA-Z0-9]*[_^]`, single-char vars `\b[a-zA-Z]\b`; also camelCase splits → try `W_q`, `W_{query}` variants
- [X] T014 [P] Create `src/util/latexRenderer.ts` — `renderToString(latex: string): string` using `katex.renderToString(latex, { output: "html", throwOnError: false })`; returns KaTeX HTML for use in `vscode.MarkdownString` with `isTrusted: true`
- [X] T015 [P] Create `src/api/ResearchAnalyserClient.ts` — implement `IResearchAnalyserClient` interface from `specs/002-vscode-extension/contracts/api-client.md`: `health()` (2 s timeout), `getLatestReport()` (5 s timeout), `analyse()` (300 s timeout), `analyseStream()` stubs; read `researchAnalyser.apiUrl` from workspace config; implement error-handling table (200/404/422/500/network) per contract

**Checkpoint**: Build succeeds (`npm run build`) with no TypeScript errors — foundation ready for user story implementation.

---

## Phase 3: US1 — Load Report + Research Context Sidebar (Priority: P1) 🎯 MVP

**Goal**: User can load an `analysis_report.json` (from file or auto-loaded from API) and see paper info, equations, and spec sections in the sidebar TreeView within 500 ms.

**Independent Test**: Run `researchAnalyser.loadReport` → pick a sample `analysis_report.json` → sidebar populates with Paper/Equations/Spec Sections nodes and correct data within 500 ms (AC-1).

- [X] T016 [US1] Implement `loadReportCommand` in `src/commands/loadReportCommand.ts` — opens `vscode.window.showOpenDialog` filtered to `*.json`, reads file, calls `ReportStore.load(report)`, shows `showInformationMessage` on success and `showErrorMessage` on failure per `specs/002-vscode-extension/contracts/commands.md #researchAnalyser.loadReport`
- [X] T017 [P] [US1] Implement `ResearchAnalyserClient.getLatestReport()` in `src/api/ResearchAnalyserClient.ts` — `GET /report/latest`, return `AnalysisReport | null` (null on 404), 5 s timeout per `specs/002-vscode-extension/contracts/api-client.md`
- [X] T018 [P] [US1] Create `src/providers/ResearchTreeDataProvider.ts` — `vscode.TreeDataProvider<ResearchTreeItem>`; root nodes: **Paper** (title/authors/score), **Equations** (eq-N children), **Spec Sections** (§X.Y children); listens to `ReportStore.onDidChange`; clicking an equation node fires `researchAnalyser.openPanel` with scroll-to-equation context
- [X] T019 [US1] Register sidebar ActivityBar view container and `ResearchTreeDataProvider` in `src/extension.ts`; add `"views"` and `"viewsContainers"` to `package.json`
- [X] T020 [US1] Implement auto-load on activation in `src/extension.ts` — if `researchAnalyser.autoLoadLatestReport` is `true`, call `client.getLatestReport()` after activation, load into `ReportStore` if not null, catch network errors silently

**Checkpoint**: Load report → sidebar shows Paper/Equations/Spec Sections within 500 ms (AC-1).

---

## Phase 4: US2 — Equation Hover Provider (Priority: P2)

**Goal**: Hovering over a known symbol (e.g. `alpha`, `W_q`) in any supported language file shows a rendered LaTeX equation card within 200 ms. Unknown symbols show nothing.

**Independent Test**: Open a `.py` file, hover over a symbol that exists in the loaded report → hover card appears with rendered LaTeX, equation label, and section. Hover over `foobar` → no hover card (AC-2, AC-3).

- [X] T021 [P] [US2] Create `src/providers/EquationHoverProvider.ts` — `vscode.HoverProvider`; `provideHover()` looks up hovered word in `ReportStore.getEquationIndex()`; if found, renders LaTeX via `latexRenderer.renderToString()`, builds `vscode.MarkdownString` (`isTrusted: true`) with equation card (symbol, eq-id, section, rendered HTML, Copy LaTeX / Show in Panel links); returns `undefined` immediately if store is empty
- [X] T022 [US2] Hook `ReportStore.onDidChange` to rebuild `EquationIndex` via `symbolIndex.buildSymbolIndex()` and store result in `EquationHoverProvider` cache in `src/providers/EquationHoverProvider.ts`
- [X] T023 [US2] Register `EquationHoverProvider` in `src/extension.ts` for each language in `researchAnalyser.hoverLanguages` config array (default: `python`, `typescript`, `javascript`, `cpp`, `rust`)

**Checkpoint**: Hover over known symbol → card within 200 ms (AC-2). Hover over unknown → nothing (AC-3).

---

## Phase 5: US3 — Spec.md Live Renderer (Priority: P3)

**Goal**: Opening any `spec.md` or `*_spec.md` file provides a split view — editable text on the left, KaTeX-rendered preview on the right — with no CDN requests (offline).

**Independent Test**: Open a sample `spec.md` with `$$...$$ ` blocks → right pane shows rendered equations; all `$...$` inline math renders; no network requests in DevTools (AC-4, AC-9).

- [X] T024 [US3] Create `src/webview/panel.html` — HTML shell loading `katex.min.css`, `katex.min.js`, and `panel.js` via `vscode-resource:` URIs; message handler skeleton (`window.addEventListener('message', ...)`) per `specs/002-vscode-extension/research.md R-05`
- [X] T025 [P] [US3] Create `src/webview/panel.ts` — webview-side JS; handles `ToWebviewMessage.loadReport`, `scrollToEquation`, `clearReport`; renders markdown content with `$$...$$` replaced by KaTeX `renderToString()` calls; sends `FromWebviewMessage.ready`, `insertEquation`, `openExternal` per `specs/002-vscode-extension/contracts/webview-messages.md`
- [X] T026 [US3] Create `src/providers/SpecDocumentProvider.ts` — `vscode.CustomTextEditorProvider`; `resolveCustomTextEditor()` creates a `WebviewPanel` showing rendered spec content; listens to `vscode.workspace.onDidChangeTextDocument` to re-render on edits; sets `webview.options.localResourceRoots` to extension `katex/` dir per `specs/002-vscode-extension/research.md R-03`
- [X] T027 [US3] Register `SpecDocumentProvider` in `package.json` `"customEditors"` array (selector: `**/spec.md` and `**/*_spec.md`, priority: `"option"`) and in `src/extension.ts` `vscode.window.registerCustomEditorProvider()`
- [X] T028 [P] [US3] Add inline equation decorations to text editor pane in `src/providers/SpecDocumentProvider.ts` — after lines matching `## Equations` or `### eq-N`, inject a right-aligned `vscode.DecorationInstanceRenderOptions.after` decoration with a small KaTeX-rendered preview (muted style)

**Checkpoint**: Open `spec.md` → all `$$...$$` blocks render via KaTeX; no CDN requests; text pane remains editable (AC-4, AC-9).

---

## Phase 6: US4 — Equation Insertion + Research Panel (Priority: P4)

**Goal**: `⇧⌘Q` opens a QuickPick list of all equations; selecting one inserts it at the cursor in the active editor in the chosen format (comment/docstring/raw). `⇧⌘E` opens the full ResearchPanel with Summary/Equations/Diagrams/Peer Review/Spec tabs.

**Independent Test**: Press `⇧⌘Q` with report loaded → QuickPick shows all equations with section and LaTeX preview → select one → choose "comment block" → `# $$...$$` inserted at cursor (AC-5).

- [X] T029 [US4] Create `src/panels/ResearchPanel.ts` — `WebviewPanel` singleton; `createOrShow()` either reveals existing panel or creates new one; sends `loadReport` message to webview on `ReportStore.onDidChange`; handles `FromWebviewMessage.insertEquation` (calls active editor insert) and `openExternal` (calls `vscode.env.openExternal`)
- [X] T030 [P] [US4] Extend `src/webview/panel.ts` to render full ResearchPanel tabs: **Summary** (abstract/methodology/results cards), **Equations** (KaTeX-rendered list with Copy LaTeX + Insert as comment buttons), **Diagrams** (img tags from `diagram.image_path`), **Peer Review** (score bar, strengths/weaknesses), **Spec** (full spec.md rendered with KaTeX) — styled with `--vscode-*` CSS variables
- [X] T031 [US4] Implement `pickEquationCommand` in `src/commands/pickEquationCommand.ts` — builds `vscode.QuickPickItem[]` from `ReportStore` equations (label: `eq-N §Section`, description: truncated LaTeX); on selection shows second QuickPick for format (`comment block` / `docstring` / `raw`); inserts result at active editor cursor via `editor.edit()` per `specs/002-vscode-extension/contracts/commands.md #researchAnalyser.pickEquation`
- [X] T032 [P] [US4] Implement `copyEquationCommand` in `src/commands/pickEquationCommand.ts` — copies selected equation's `.latex` to clipboard via `vscode.env.clipboard.writeText()`
- [X] T033 [US4] Wire `openPanel` command and keybindings (`⇧⌘E`, `⇧⌘Q`) in `src/extension.ts` and `package.json` `"keybindings"` + `"menus"."editor/context"` per `specs/002-vscode-extension/contracts/commands.md`

**Checkpoint**: `⇧⌘Q` → pick equation → inserts at cursor (AC-5). `⇧⌘E` → ResearchPanel opens with Summary and Equations tabs.

---

## Phase 7: US5 — Trigger Analysis from IDE (Priority: P5)

**Goal**: `⇧⌘R` triggers `POST /analyse/stream`, streams SSE progress updates in a VS Code progress notification, loads report on completion, and prompts to auto-start the server if it isn't running.

**Independent Test**: Start Research Analyser API (`uvicorn research_analyser.api:app`), press `⇧⌘R`, enter an arXiv ID → progress notifications appear → ResearchPanel opens with results (AC-6). Kill API, press `⇧⌘R` → "Start server?" prompt appears (AC-7).

- [X] T034 [US5] Implement SSE stream reader in `src/api/ResearchAnalyserClient.ts` — `analyseStream()`: `fetch(url, { method: 'POST', signal })`, `response.body.getReader()`, parse `event:` / `data:` lines, call `onProgress(ProgressEvent)` for `event: progress`, resolve with `AnalysisReport` on `event: complete`, reject with error message on `event: error` per `specs/002-vscode-extension/contracts/api-client.md`
- [X] T035 [P] [US5] Implement `ResearchAnalyserClient.analyse()` blocking variant in `src/api/ResearchAnalyserClient.ts` — `POST /analyse` with 300 s timeout; parse response JSON as `AnalysisReport`
- [X] T036 [US5] Implement `analyseCommand` in `src/commands/analyseCommand.ts` — `showInputBox` for source (arXiv/URL/DOI/path); call `client.health()` first; if offline show `showWarningMessage("Research Analyser server not running. Start it?")` with "Start" button → create `vscode.Task` running `uvicorn research_analyser.api:app`, retry after 5 s; if online call `analyseStream()` wrapped in `vscode.window.withProgress({ location: Notification })`, update progress title from `ProgressEvent.message` per `specs/002-vscode-extension/contracts/commands.md #researchAnalyser.analyse`
- [X] T037 [US5] On `event: complete` in `analyseCommand`: call `ReportStore.load(report)`, call `ResearchPanel.createOrShow()`, show `showInformationMessage("Analysis complete — score · N equations")` per `specs/002-vscode-extension/spec.md §6`
- [X] T038 [P] [US5] Add `researchAnalyser.serverRunning` context key management in `src/extension.ts` — call `client.health()` on activation, set `vscode.commands.executeCommand('setContext', 'researchAnalyser.serverRunning', true/false)`; also update after `analyseCommand` health check

**Checkpoint**: `⇧⌘R` → SSE progress updates at least every 5 s → ResearchPanel opens on completion (AC-6). Offline → "Start server?" prompt (AC-7).

---

## Phase 8: US6 — Implementation Coverage Tracker (Priority: P6)

**Goal**: Developers annotate code with `// @implements §X.Y`; the sidebar shows which spec sections are covered/uncovered; gutter icons mark covered lines; `markImplementsCommand` inserts the annotation with a section picker.

**Independent Test**: Add `// @implements §3.1` to a file → sidebar Spec Sections node shows §3.1 as covered (green check); uncovered sections show grey circle. Run `researchAnalyser.markImplements` → section picker → `// @implements §X.Y` inserted at cursor (AC-8).

- [X] T039 [US6] Implement `CoverageDecorator` in `src/decorators/CoverageDecorator.ts` — uses `vscode.workspace.findFiles()` to scan workspace for `@implements §X.Y` regex across all text files; builds `AnnotationMap` (section ref → `CodeLocation[]`); applies `vscode.TextEditorDecorationType` gutter icon (green check) at matching lines; listens to `vscode.workspace.onDidSaveTextDocument` to re-scan; pushes `onDidChange` event to `ResearchTreeDataProvider`
- [X] T040 [P] [US6] Add **Spec Sections** coverage node to `src/providers/ResearchTreeDataProvider.ts` — reads `AnnotationMap` from `CoverageDecorator`; for each section in loaded report shows ✓ (covered) or ○ (uncovered) with total count in node label
- [X] T041 [US6] Implement `markImplementsCommand` in `src/commands/markImplementsCommand.ts` — `showQuickPick` with all sections from loaded `AnalysisReport`; inserts `// @implements §X.Y` at active editor cursor position using `editor.edit()` per `specs/002-vscode-extension/contracts/commands.md #researchAnalyser.markImplements`
- [X] T042 [P] [US6] Add gutter icon SVG assets (`covered.svg`, `uncovered.svg`) to `src/assets/` and register `vscode.window.createTextEditorDecorationType({ gutterIconPath })` in `CoverageDecorator.ts`

**Checkpoint**: `@implements §X.Y` annotations counted correctly; coverage sidebar shows covered/uncovered sections; gutter icons appear on annotated lines (AC-8).

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Configuration, packaging, CI/CD, and the backend change required for SSE streaming.

- [X] T043 Add all `researchAnalyser.*` configuration properties to `package.json` `"contributes"."configuration"`: `apiUrl`, `autoLoadLatestReport`, `reportSearchPaths`, `hoverEnabled`, `hoverLanguages`, `inlineDecorationsEnabled`, `katexFontSize`, `specFileGlob`, `insertFormat` with types/defaults per `specs/002-vscode-extension/spec.md §7`
- [X] T044 [P] Add `/analyse/stream` SSE endpoint to `research_analyser/api.py` (in the Research Analyser Python project) using `sse_starlette.sse.EventSourceResponse` per `specs/002-vscode-extension/contracts/api-client.md §Backend Change Required`; add `sse-starlette` to `requirements.txt`
- [X] T045 [P] Write `README.md` for the extension repository (installation, configuration, usage for each command, screenshots)
- [X] T046 [P] Create `.github/workflows/ci.yml` — on push: `npm ci`, `npm run lint`, `npm run build`, `npm test`, `vsce package` (dry-run)
- [X] T047 Run `vsce package` → validate `research-analyser-0.1.0.vsix` installs cleanly via `code --install-extension`
- [X] T048 [P] Run `specs/002-vscode-extension/quickstart.md` validation checklist end-to-end and resolve any gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Requires Phase 1 complete — **BLOCKS** all user stories
- **User Stories (Phases 3–8)**: All require Phase 2 complete; can proceed sequentially (P1 → P2 → ... → P6)
- **Polish (Phase 9)**: Requires all desired user story phases complete

### User Story Dependencies

| Story | Phase | Depends On | Integration Notes |
|-------|-------|-----------|-------------------|
| US1 Load Report + Sidebar | 3 | Phase 2 | No cross-story deps |
| US2 Hover Provider | 4 | Phase 2, T011 (ReportStore) | Reads from ReportStore |
| US3 Spec Renderer | 5 | Phase 2 | Uses KaTeX webview |
| US4 Equation Insertion | 6 | Phase 2; US1 recommended (needs loaded report) | ReportStore data |
| US5 Analysis Trigger | 7 | Phase 2; T015 (API client fully implemented) | Loads into ReportStore |
| US6 Coverage Tracker | 8 | Phase 2; US1 (needs section list from report) | Reads sections from ReportStore |

### Within Each User Story

- Core files before integrations with ReportStore
- Provider/command logic before registration in `extension.ts`
- `extension.ts` registration last (depends on all providers/commands being complete)

### Parallel Opportunities

- T003, T004, T005 (Phase 1) — all in different config files
- T013, T014, T015 (Phase 2) — `symbolIndex.ts`, `latexRenderer.ts`, `ResearchAnalyserClient.ts` are independent
- T021, T022 with T024, T025 — hover and spec renderer are independent
- T044 (backend change) can be worked in parallel with any frontend task

---

## Parallel Example: Phase 2 (Foundational)

```
# After T010 (types) and T011 (ReportStore) complete, run in parallel:
Task T013: symbolIndex.ts  (pure utility, no VS Code API needed)
Task T014: latexRenderer.ts  (pure KaTeX wrapper, no VS Code API needed)
Task T015: ResearchAnalyserClient.ts  (HTTP client, no VS Code API needed)
Task T012: extension.ts skeleton  (registers commands using stubs from T015)
```

## Parallel Example: User Story 3 (Spec Renderer)

```
# T024 (panel.html) and T025 (panel.ts) can run in parallel:
Task T024: panel.html — HTML shell with vscode-resource: KaTeX links
Task T025: panel.ts — webview JS rendering markdown + KaTeX
# Then T026 (SpecDocumentProvider) wires them together
```

---

## Implementation Strategy

### MVP First (US1 + US4 — Load Report + Panel)

1. Complete **Phase 1**: Setup
2. Complete **Phase 2**: Foundational — types, ReportStore, API client skeleton, esbuild
3. Complete **Phase 3** (US1): `loadReportCommand` + `ResearchTreeDataProvider` + auto-load
4. Complete **Phase 6** (US4): `ResearchPanel` + `pickEquationCommand` (insert equation at cursor)
5. **STOP and VALIDATE**: Load a report → sidebar populates → `⇧⌘Q` inserts equation ✓
6. Demo to user; ship as v0.1

### Incremental Delivery

| Increment | Phases | New Value |
|-----------|--------|-----------|
| v0.1 MVP | 1+2+3+6 | Load report → sidebar + equation insertion |
| v0.2 | +4 | Hover over symbols → LaTeX card |
| v0.3 | +5 | Open spec.md → KaTeX rendered |
| v0.4 | +7 | `⇧⌘R` triggers analysis with live progress |
| v0.5 | +8 | `@implements` coverage tracking |
| v1.0 | +9 | Package + publish to Marketplace |

---

## Task Count Summary

| Phase | Tasks | Parallel |
|-------|-------|---------|
| Phase 1: Setup | 9 | 6 |
| Phase 2: Foundational | 6 | 4 |
| Phase 3: US1 | 5 | 2 |
| Phase 4: US2 | 3 | 1 |
| Phase 5: US3 | 5 | 2 |
| Phase 6: US4 | 5 | 2 |
| Phase 7: US5 | 5 | 2 |
| Phase 8: US6 | 4 | 2 |
| Phase 9: Polish | 6 | 4 |
| **Total** | **48** | **25** |

---

## Notes

- `[P]` tasks touch different files and have no incomplete shared dependencies
- Each user story is independently completable and testable against its Acceptance Criteria
- `extension.ts` is the **last** file to update in each phase (registration wires everything together)
- Commit after each checkpoint (end of each phase) for clean rollback points
- T044 (backend SSE endpoint) should be done before Phase 7 (US5) testing begins
