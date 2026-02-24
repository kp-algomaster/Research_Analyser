# Implementation Plan: VS Code Extension — Research Analyser Integration

**Branch**: `002-vscode-extension` | **Date**: 2026-02-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-vscode-extension/spec.md`

---

## Summary

Build a VS Code extension (`research-analyser-vscode`) that surfaces Research Analyser
output — equations, methodology, peer-review scores, spec sections — directly in the
editor. The extension lives in a **separate TypeScript repository** and connects to the
Research Analyser FastAPI backend (`research_analyser/api.py`) over HTTP/SSE.

Core value loop:
1. Developer analyses a paper with Research Analyser → `AnalysisReport` JSON produced
2. Extension loads that report (auto-load or manual)
3. Hover over any symbol (`alpha`, `W_q`) → LaTeX equation card appears
4. Open `spec.md` → equations render via KaTeX, not raw `$...$` strings
5. `⇧⌘Q` → pick any equation and insert it at cursor as a comment/docstring
6. `@implements §3.2` annotations tracked → sidebar shows coverage gaps

---

## Technical Context

**Language/Version**: TypeScript 5.4+ / Node.js 20 LTS
**Primary Dependencies**: `vscode` API 1.85+, KaTeX 0.16 (bundled), `esbuild` 0.21
**Storage**: Local filesystem (`analysis_report.json`) + in-memory `ReportStore` singleton
**Testing**: `@vscode/test-electron` 2.x + Mocha 10 + `sinon` for mocking
**Target Platform**: VS Code 1.85+ desktop (macOS, Linux, Windows); no web extension
**Project Type**: VS Code extension (`.vsix` package published to Marketplace + Open VSX)
**Performance Goals**: Activation < 300 ms; hover response < 200 ms; report load < 500 ms
**Constraints**: All KaTeX rendering offline (no CDN); zero runtime npm dependencies in bundle
**Scale/Scope**: Single-user tool; one loaded report at a time; ≤ 500 equations per report

---

## Constitution Check

*This extension is a separate TypeScript project. Python-specific constitution rules
(Pipeline-First, Async-By-Default via asyncio) do not apply directly. The spirit of
each principle is mapped below.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Pipeline-First | ✅ ADAPTED | All report access goes through `ReportStore` singleton — no direct cross-component imports |
| II. Async-By-Default | ✅ COMPLIANT | All API calls use `async/await`; VS Code APIs are callback/Promise-based |
| III. Fail-Safe Optional | ✅ COMPLIANT | Hover, decorations, and coverage are all optional; report load failure shows notification, not crash |
| IV. Typed Data Contracts | ✅ COMPLIANT | TypeScript interfaces mirror `AnalysisReport` models; all Webview ↔ extension messages typed |
| V. Spec-Driven | ✅ COMPLIANT | `spec.md` → `plan.md` → `tasks.md` → implement workflow followed |
| VI. Ship-and-Verify | ⬜ PENDING | Will apply: all tasks marked before push; `npm test` + `eslint` must be clean |

**Complexity Justification**: Separate TypeScript repo is justified — the extension uses
VS Code's Node.js runtime, incompatible with the Python package structure. The API boundary
(`localhost:8000`) is the integration seam; both projects remain independently deployable.

---

## Project Structure

### Documentation (this feature)

```text
specs/002-vscode-extension/
├── plan.md              ← this file
├── research.md          ← Phase 0: technology decisions
├── data-model.md        ← Phase 1: TypeScript interfaces
├── quickstart.md        ← Phase 1: dev setup guide
├── contracts/
│   ├── commands.md      ← VS Code command registry contract
│   ├── webview-messages.md  ← Webview ↔ extension message protocol
│   └── api-client.md   ← Research Analyser REST API client contract
└── tasks.md             ← Phase 2: task breakdown (via /speckit.tasks)
```

### Source Code (new repository: `research-analyser-vscode`)

```text
research-analyser-vscode/
├── src/
│   ├── extension.ts              ← activate() / deactivate() entry point
│   ├── store/
│   │   └── ReportStore.ts        ← singleton: holds AnalysisReport, emits change events
│   ├── providers/
│   │   ├── EquationHoverProvider.ts   ← HoverProvider: symbol → LaTeX card
│   │   ├── SpecDocumentProvider.ts    ← CustomTextEditorProvider: spec.md KaTeX
│   │   └── ResearchTreeDataProvider.ts ← TreeDataProvider: sidebar tree
│   ├── panels/
│   │   └── ResearchPanel.ts      ← WebviewPanel: full report viewer
│   ├── commands/
│   │   ├── analyseCommand.ts     ← POST /analyse + SSE progress
│   │   ├── pickEquationCommand.ts← QuickPick equations + insert
│   │   ├── loadReportCommand.ts  ← load analysis_report.json from disk
│   │   └── markImplementsCommand.ts ← insert @implements §X.Y
│   ├── decorators/
│   │   └── CoverageDecorator.ts  ← gutter icons for @implements annotations
│   ├── api/
│   │   └── ResearchAnalyserClient.ts ← HTTP + SSE client for localhost:8000
│   ├── util/
│   │   ├── symbolIndex.ts        ← build symbol → equation map from LaTeX
│   │   └── latexRenderer.ts      ← KaTeX SVG rendering (Node.js side)
│   └── webview/
│       ├── panel.html            ← WebviewPanel HTML shell
│       ├── panel.ts              ← webview-side JS (compiled separately)
│       └── katex/                ← bundled KaTeX 0.16 assets
├── tests/
│   ├── unit/
│   │   ├── ReportStore.test.ts
│   │   ├── symbolIndex.test.ts
│   │   └── latexRenderer.test.ts
│   └── integration/
│       ├── hover.test.ts         ← @vscode/test-electron hover tests
│       └── commands.test.ts
├── package.json
├── tsconfig.json
├── esbuild.config.js
├── .eslintrc.json
└── README.md
```

**Structure Decision**: Single TypeScript project (Option 1). No backend or mobile layer.
All VS Code extension code in `src/`; webview assets colocated under `src/webview/`.

---

## Implementation Phases

### Phase 1 — MVP Core (commands + panel + report load)
Deliverables: extension activates, report loads, ResearchPanel shows Summary+Equations, equation picker inserts at cursor.

### Phase 2 — Intelligence (hover + spec.md renderer)
Deliverables: `EquationHoverProvider` with symbol index; `SpecDocumentProvider` with KaTeX decorations; sidebar TreeView.

### Phase 3 — Analysis trigger (API client + SSE)
Deliverables: `analyseCommand` calls API, streams progress via SSE; auto-start server prompt.

### Phase 4 — Coverage tracking & publish
Deliverables: `CoverageDecorator`; `markImplementsCommand`; `@vscode/test-electron` suite passing; `vsce package` → `.vsix`; publish to Marketplace.

---

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|------------|--------------------------------------|
| KaTeX bundled offline | Spec AC-9: no CDN | CDN fails in air-gapped / restricted corp environments |
| `CustomTextEditorProvider` for spec.md | Split editable+rendered view in single panel | `vscode.previewHtml` deprecated; standard preview only supports read-only |
| Separate webview JS bundle | Webview has its own JS sandbox | Cannot share Node.js modules with extension host process |
| SSE for analysis progress | Streaming updates; no polling lag | WebSocket overkill; FastAPI native SSE matches existing API patterns |
