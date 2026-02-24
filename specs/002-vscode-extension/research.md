# Phase 0 Research — VS Code Extension: Research Analyser Integration

---

## R-01: VS Code Extension Build Tooling — esbuild vs webpack

**Decision**: Use **esbuild** (not webpack)
**Rationale**:
- esbuild is 10–100× faster than webpack; extension rebuild < 200 ms in watch mode
- VS Code's official generator now defaults to esbuild (`yo code` 2024+)
- Simpler config: single `esbuild.config.js`, no loader plugins needed for our use case
- Tree-shaking adequate for our dependencies (KaTeX, no heavy runtime deps)

**Configuration**:
```js
// esbuild.config.js
require("esbuild").build({
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "out/extension.js",
  external: ["vscode"],      // vscode is provided by the host
  platform: "node",
  target: "node20",
  sourcemap: true,
  minify: process.env.NODE_ENV === "production",
});
```
Webview JS compiled separately (same esbuild, `platform: "browser"`).

---

## R-02: KaTeX Integration — Server-side vs Client-side

**Decision**: **Dual rendering** — server-side (Node.js) for hover cards; client-side (webview) for panels.

**Rationale**:
- Hover cards must return a `vscode.MarkdownString`; KaTeX can render to HTML string in Node.js (`katex.renderToString(latex, { output: "html" })`) which Markdown preview supports via `isTrusted: true`
- WebviewPanel and CustomTextEditorProvider have full browser JS context → standard KaTeX client-side bundle
- Bundling KaTeX in both places is acceptable (≈ 250 KB gzipped); no CDN required → AC-9 compliant

**KaTeX version**: 0.16.x (latest stable, supports all LaTeX math constructs used in academic papers)

**Fonts**: Bundle KaTeX fonts in `src/webview/katex/fonts/`; reference via `vscode-resource:` URI in webviews.

---

## R-03: CustomTextEditorProvider vs WebviewEditorProvider

**Decision**: Use `CustomTextEditorProvider` (not `WebviewEditorProvider` / deprecated `WebviewPanel` approach)

**Rationale**:
- `CustomTextEditorProvider` is the VS Code 1.80+ official API for custom editors with document model
- Provides `TextDocument` access → we can edit the markdown source
- Split pane (text on left, rendered preview on right) achieved via `WebviewPanel` created inside the provider
- `vscode.window.showTextDocument` + `CustomTextEditorProvider.resolveCustomTextEditor` = correct pattern

**Registration**:
```json
"customEditors": [{
  "viewType": "researchAnalyser.specRenderer",
  "displayName": "Spec Renderer",
  "selector": [{ "filenamePattern": "**/spec.md" }, { "filenamePattern": "**/*_spec.md" }],
  "priority": "option"   // "option" = user chooses; "default" = always opens this way
}]
```
`"priority": "option"` so standard markdown preview still works; user right-clicks → "Open with Spec Renderer".

---

## R-04: Symbol Extraction from LaTeX

**Decision**: Regex-based extraction (not full LaTeX parser)

**Rationale**: A full LaTeX parser (e.g., `latex-utensils`) adds 2 MB to bundle and handles edge cases (macros, environments) we don't need. Regex covers 95% of academic paper variable patterns.

**Symbol extraction algorithm**:
```typescript
function extractSymbols(latex: string): string[] {
  const symbols = new Set<string>();

  // Greek letters: \alpha, \beta, \mathbf{W}, etc.
  for (const m of latex.matchAll(/\\([a-zA-Z]+)/g)) symbols.add(m[1]);

  // Plain identifiers: W_q, x_i, h_t (split on _ and ^)
  for (const m of latex.matchAll(/\b([a-zA-Z][a-zA-Z0-9]*)[_^]/g)) symbols.add(m[1]);

  // Single-char variables: $x$, $y$, $z$
  for (const m of latex.matchAll(/\b([a-zA-Z])\b/g)) symbols.add(m[1]);

  return [...symbols];
}
```

**Index lookup**: Map `symbol.toLowerCase()` and also camelCase splits (`queryWeight` → [`query`, `Weight`, `W`]).

---

## R-05: Webview ↔ Extension Communication

**Decision**: Typed message-passing via `postMessage` / `onDidReceiveMessage`

**Rationale**: VS Code Webview is sandboxed; only `postMessage` crosses the boundary. Define a discriminated union for all message types → compile-time safety.

**Pattern**:
```typescript
// shared/messages.ts (imported by both extension and webview bundle)
export type ToWebview =
  | { type: "loadReport"; report: AnalysisReport }
  | { type: "scrollToEquation"; id: string }
  | { type: "clearReport" };

export type FromWebview =
  | { type: "ready" }
  | { type: "insertEquation"; latex: string; format: InsertFormat }
  | { type: "openExternal"; url: string };
```

---

## R-06: Analysis Trigger — SSE vs Polling

**Decision**: **SSE** (Server-Sent Events) from FastAPI `/analyse/stream`

**Rationale**:
- FastAPI supports `EventSourceResponse` natively via `sse-starlette`
- SSE is unidirectional (server → client) and maps perfectly to analysis progress push
- Node.js `fetch` with `response.body.getReader()` handles SSE without extra libraries
- Polling would require a `/progress` endpoint + timer management in VS Code

**Note**: The Research Analyser API (`research_analyser/api.py`) needs a `/analyse/stream` SSE endpoint added. This is a Research Analyser backend task, not extension-side. The extension degrades gracefully to polling if SSE is unavailable.

---

## R-07: Testing Strategy

**Decision**: Unit tests with mocked VS Code API + integration tests with `@vscode/test-electron`

**Rationale**:
- `@vscode/test-electron` launches real VS Code instance; needed for TreeView, Hover, Webview tests
- Unit tests (pure logic: symbol index, report parsing, LaTeX rendering) run without VS Code → fast feedback
- Mock pattern: `jest-mock` on `vscode` module for unit tests

**Test runner**: Mocha (standard for VS Code extensions) not Jest, since `@vscode/test-electron` integrates with Mocha. ESM-compatible via `ts-mocha`.

---

## R-08: Extension Activation Strategy

**Decision**: `"onStartupFinished"` + lazy provider registration

**Rationale**:
- `"onStartupFinished"` activates after VS Code startup — doesn't block editor opening
- All heavy providers (HoverProvider, TreeDataProvider) registered in `activate()` but their logic executes lazily (on first hover, on first tree expansion)
- `EquationHoverProvider.provideHover` returns `undefined` immediately if `ReportStore` is empty
- Activation budget: < 300 ms (AC-10) — measured with `vscode-extension-telemetry`

---

## R-09: VS Code Marketplace Publication

**Decision**: Publish to both **VS Code Marketplace** (Microsoft) and **Open VSX** (Eclipse Foundation)

**Rationale**:
- Open VSX required for VS Code forks: VSCodium, Gitpod, GitHub Codespaces
- `vsce publish` for Marketplace; `ovsx publish` for Open VSX
- Publisher ID: `kp-algomaster` (matches GitHub org)
- CI/CD: GitHub Actions workflow on tag push (`v*.*.*`) runs `vsce package` → `ovsx publish`

---

## Resolved Clarifications

| # | Question | Resolution |
|---|----------|------------|
| 1 | Build tool: esbuild or webpack? | **esbuild** (faster, simpler, VS Code default) |
| 2 | KaTeX: server-side or client-side? | **Both** — Node.js for hover, browser for panels |
| 3 | Custom editor API version? | **CustomTextEditorProvider** (VS Code 1.80+) |
| 4 | Symbol extraction: parser or regex? | **Regex** (sufficient, lightweight) |
| 5 | Progress streaming: SSE or polling? | **SSE** — requires `/analyse/stream` added to API |
| 6 | Test framework: Mocha or Jest? | **Mocha** (native @vscode/test-electron integration) |
| 7 | Activation event? | **onStartupFinished** + lazy providers |
| 8 | Publish target? | **Marketplace + Open VSX** |
