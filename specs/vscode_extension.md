# VS Code Extension — Research Analyser Integration
**Spec version:** 1.0
**Status:** Draft
**Depends on:** Research Analyser API (`research_analyser/api.py`), analysis output format (`AnalysisReport`)

---

## 1. Purpose

Bridge the gap between a research paper analysis and its software implementation.
When a developer builds code based on a paper, the Research Analyser extension surfaces
the paper's equations, methodology, key findings, and spec directly inside VS Code —
reducing context-switching between browser/PDF and editor.

### 1.1 Primary Use Cases

| Use Case | Description |
|----------|-------------|
| **Equation reference while coding** | Hover over a symbol (`alpha`, `W_q`) to see its LaTeX definition from the paper |
| **Spec.md with live equations** | Open the generated `spec.md` and see LaTeX rendered inline, not raw `$...$` strings |
| **Research context sidebar** | Quick-access panel: abstract, methodology, score, key findings |
| **Equation insertion** | Pick an equation from the paper and insert it as a docstring/comment at cursor |
| **Trigger analysis from IDE** | Run Research Analyser on a PDF/URL without leaving VS Code |
| **Implementation coverage** | Tag functions/files as "implements §3.2" and see uncovered spec sections |

---

## 2. Architecture

```
VS Code Extension (TypeScript)
    ├── ResearchPanel         — WebviewPanel: full report viewer with rendered equations
    ├── EquationHoverProvider — HoverProvider: symbol → LaTeX tooltip
    ├── SpecDocumentProvider  — CustomTextEditorProvider: spec.md with inline equation renders
    ├── EquationPickerCommand — QuickPick: browse + insert equations as comments
    ├── AnalysisTriggerCommand— calls Research Analyser REST API, streams progress
    ├── CoverageDecorator     — gutter icons marking "implements §X.Y" annotations
    └── ReportStore           — singleton: holds loaded AnalysisReport JSON in memory

Research Analyser API (localhost:8000 or configurable)
    GET  /health
    POST /analyse          — triggers analysis, returns AnalysisReport JSON
    GET  /report/latest    — returns the most recent AnalysisReport JSON
    GET  /equations        — returns all extracted equations
```

### 2.1 Data Flow

```
User opens PDF / pastes URL
    → Extension calls POST /analyse (streams progress via SSE)
    → On completion: AnalysisReport stored in ReportStore
    → ResearchPanel, HoverProvider, SpecDocumentProvider all refresh from ReportStore
    → Equation symbols extracted → HoverProvider index built
    → spec.md (if generated) opened with equation decorations applied
```

---

## 3. Extension Manifest (`package.json` highlights)

```json
{
  "name": "research-analyser",
  "displayName": "Research Analyser",
  "publisher": "kp-algomaster",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Other", "Visualization"],
  "activationEvents": [
    "onStartupFinished",
    "onLanguage:markdown",
    "onCommand:researchAnalyser.analyse"
  ],
  "contributes": {
    "commands": [/* see §4 */],
    "views": { "researchAnalyser": [/* see §5 */] },
    "configuration": {/* see §7 */},
    "customEditors": [/* spec.md renderer */],
    "menus": { "editor/context": [/* Insert Equation */] }
  }
}
```

---

## 4. Commands

| Command ID | Title | Keyboard Shortcut | Description |
|-----------|-------|-------------------|-------------|
| `researchAnalyser.analyse` | Research Analyser: Analyse Paper | `⇧⌘R` | Prompt for PDF path / URL, call API, stream progress |
| `researchAnalyser.loadReport` | Research Analyser: Load Report JSON | — | Open file picker to load a saved `analysis_report.json` |
| `researchAnalyser.openPanel` | Research Analyser: Open Report Panel | `⇧⌘E` | Show/focus ResearchPanel WebviewPanel |
| `researchAnalyser.pickEquation` | Research Analyser: Insert Equation | `⇧⌘Q` | QuickPick from loaded equations, insert at cursor |
| `researchAnalyser.clearReport` | Research Analyser: Clear Loaded Report | — | Reset ReportStore, hide decorators |
| `researchAnalyser.copyEquation` | Research Analyser: Copy Equation (LaTeX) | — | Copy selected equation to clipboard |
| `researchAnalyser.markImplements` | Research Analyser: Mark as Implements §… | — | Add `// @implements §X.Y` annotation at cursor |

---

## 5. Views & UI

### 5.1 Research Analyser Sidebar (Activity Bar icon)

```
RESEARCH ANALYSER                          [⟳ Analyse]
─────────────────────────────────────────────────────
▸ Paper
    Title: Unifying Color and Lightness...
    Authors: Z. Cui, S. Liu, X. Dong...
    Score:  7.4 / 10  ● Weak Accept

▸ Abstract
    High-quality image acquisition in...

▸ Methodology
    We propose a View-Adaptive Curve...

▸ Key Findings  (3)
    🔴  Novel per-view curve adjustment
    🟡  Outperforms NeRF baselines by 2.1 dB
    🟡  Paper includes 14 key equations

▸ Equations  (14)
    eq-1  · Introduction
    eq-3  · Method
    eq-7  · Loss Function
    ...
```

TreeView with three root nodes: **Paper**, **Equations**, **Spec Sections**.
Clicking an equation node opens the ResearchPanel scrolled to that equation.

### 5.2 ResearchPanel (WebviewPanel)

Full interactive report rendered in a WebviewPanel:

- **Header**: paper title, authors, score badge (colour-coded)
- **Tabs**: Summary | Equations | Diagrams | Peer Review | Spec
- **Summary tab**: Abstract / Methodology / Results cards (same dark-card style as Streamlit UI)
- **Equations tab**: Each equation rendered via KaTeX, with:
  - `Copy LaTeX` button
  - `Insert as comment` button
  - Section tag chip
  - Description if available
- **Diagrams tab**: Generated diagram images (from `diagram.image_path`)
- **Peer Review tab**: Score bar, strengths/weaknesses, dimensional scores
- **Spec tab**: Full spec.md rendered as HTML with equations via KaTeX

Technology: VS Code Webview API, KaTeX (bundled, no CDN), VS Code theme CSS variables.

### 5.3 Equation Hover Provider

Activated for all languages (`.py`, `.ts`, `.js`, `.cpp`, `.rs`, etc.).

**Index build**: On `ReportStore` load, extract all symbols from equation LaTeX:
- Regex `[a-zA-Z_][a-zA-Z_0-9]*` applied to each equation's `.latex` field
- Map symbol → list of `{ equationId, latex, label, section }` entries
- Also index camelCase splits: `queryWeight` → tries `W_q`, `W_{query}`

**Hover behaviour**:
```
User hovers over: alpha
  → Look up "alpha" in symbol index
  → Found in eq-4: \alpha = \text{learning rate}
  → Show hover card:
      ── Research Analyser ──────────────────
      **α** · eq-4 · §3 Method

      $$\alpha = \frac{\eta_0}{1 + \lambda t}$$

      Learning rate schedule for curve optimizer.
      [Copy LaTeX]  [Show in Panel]
```

Hover renders LaTeX as an SVG via KaTeX (server-side via a bundled Node.js helper, or via the Webview engine).

### 5.4 Spec Document Provider (spec.md)

When VS Code opens any file named `spec.md` or `*_spec.md`, the extension provides a custom split view:

- **Left pane**: Standard text editor (editable markdown)
- **Right pane**: Live-rendered preview with KaTeX equations
  `$...$` and `$$...$$` blocks are rendered, not displayed as raw text

This is implemented as a `CustomTextEditorProvider` registering for `**/spec.md` and `**/*_spec.md` glob patterns.

Equation blocks from the loaded AnalysisReport are also shown as **inline decorations** in the text editor pane:
- After a line containing `## Equations` or `### eq-N`, a small rendered preview is injected as a VS Code decoration (right-aligned, muted)

### 5.5 Equation Picker (QuickPick)

`⇧⌘Q` opens a QuickPick list:

```
Search equations…
─────────────────────────────────────────────
  eq-1  §Introduction   $ y = f(x; \theta) $
  eq-3  §Method         $ \mathcal{L} = ... $
  eq-7  §Loss           $ L_{total} = ... $
  …
```

On selection, user chooses insert format:
- `# $$...$$ (comment block)`
- `"""LaTeX: ...""" (docstring)`
- `Raw LaTeX string`

Equation inserted at cursor position in the active editor.

---

## 6. Analysis Trigger Flow

```
User: ⇧⌘R → "Research Analyser: Analyse Paper"
  → Input box: "PDF path, URL, arXiv ID, or DOI"
  → User enters: "2405.12345" (arXiv)
  → Extension calls: POST http://localhost:8000/analyse
    Body: { "source": "2405.12345", "options": { ... } }
  → VS Code notification: "Analysing paper…"
  → Progress notification with live message updates (SSE stream or polling GET /progress)
  → On completion: ReportStore.load(report)
  → ResearchPanel opens/refreshes
  → Success toast: "Analysis complete — 7.4/10 · 14 equations extracted"
```

If the Research Analyser API is not running:
- Extension shows: "Research Analyser server not running. Start it?"
- On confirm: spawns `uvicorn research_analyser.api:app` as a VS Code task
- Retries the API call after 5 seconds

---

## 7. Configuration

All settings under `researchAnalyser.*`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `apiUrl` | string | `"http://localhost:8000"` | Research Analyser API base URL |
| `autoLoadLatestReport` | boolean | `true` | On activation, load the most recent report from the API |
| `reportSearchPaths` | string[] | `["./output", "~/ResearchAnalyserOutput"]` | Directories to search for `analysis_report.json` |
| `hoverEnabled` | boolean | `true` | Enable equation hover on all language files |
| `hoverLanguages` | string[] | `["python","typescript","javascript","cpp","rust"]` | Languages to activate hover for |
| `inlineDecorationsEnabled` | boolean | `true` | Show equation previews as inline editor decorations |
| `katexFontSize` | string | `"1.1em"` | KaTeX font size for equation rendering |
| `specFileGlob` | string | `"**/spec.md,**/*_spec.md"` | File patterns for the custom spec renderer |
| `insertFormat` | enum | `"comment"` | Default equation insert format: `comment` \| `docstring` \| `raw` |

---

## 8. Implementation Tracking (Coverage Decorator)

Developers annotate code with `// @implements §3.2` (any language comment style).
The extension:
1. Scans workspace for `@implements §X.Y` annotations
2. Crosses them against the loaded report's sections
3. Shows coverage in the sidebar:
   ```
   ▸ Spec Sections  (6 total, 4 covered)
       ✓ §3.1  View-Adaptive Curve Model
       ✓ §3.2  Per-View Lightness Correction
       ✓ §4.1  Training Loss
       ✓ §4.2  Dataset Preparation
       ○ §5.1  Ablation Study         ← not yet implemented
       ○ §5.2  Quantitative Results   ← not yet implemented
   ```
4. Gutter icons in covered files: green check at lines with `@implements`
5. Command `researchAnalyser.markImplements` inserts `// @implements §…` with a section picker

---

## 9. Key Equations Format in spec.md

When Research Analyser generates `spec.md`, equations are embedded in a standard block:

```markdown
## Equations

### eq-1 · §Introduction
**Label:** Eq. (1)
**Section:** Introduction

$$
y = f_\theta(x)
$$

> Image-to-output mapping where $\theta$ are the learned parameters.

---

### eq-3 · §Method
**Label:** Eq. (3)
**Section:** 3.1 Proposed Method

$$
\mathcal{L}_{total} = \lambda_1 \mathcal{L}_{photo} + \lambda_2 \mathcal{L}_{reg}
$$

> Combined photometric and regularisation loss.
  $\lambda_1 = 0.8$, $\lambda_2 = 0.2$ in all experiments.

---
```

This format is:
- Renderable by standard Markdown previewers (GitHub, VS Code built-in)
- Parseable by the extension (extract equation ID, label, section, LaTeX, description)
- Searchable in the Equation Picker

---

## 10. Technology Stack

| Component | Technology |
|-----------|------------|
| Extension language | TypeScript 5+ |
| Build tool | esbuild (bundled via `vsce package`) |
| Equation rendering | KaTeX 0.16 (bundled, offline-capable) |
| Webview styling | VS Code CSS variables (`--vscode-*`) |
| API client | `fetch` (Node.js 18+ built-in) |
| Progress streaming | Server-Sent Events (SSE) from FastAPI `/analyse/stream` |
| Test framework | `@vscode/test-electron` + Mocha |
| Packaging | `vsce` for `.vsix`, published to Open VSX + VS Code Marketplace |

---

## 11. File Structure (New Extension Repository)

```
research-analyser-vscode/
├── src/
│   ├── extension.ts          — activate() entry point
│   ├── store/
│   │   └── ReportStore.ts    — singleton AnalysisReport holder
│   ├── providers/
│   │   ├── EquationHoverProvider.ts
│   │   ├── SpecDocumentProvider.ts
│   │   └── ResearchTreeDataProvider.ts
│   ├── panels/
│   │   └── ResearchPanel.ts  — WebviewPanel logic
│   ├── commands/
│   │   ├── analyseCommand.ts
│   │   ├── pickEquationCommand.ts
│   │   ├── loadReportCommand.ts
│   │   └── markImplementsCommand.ts
│   ├── decorators/
│   │   └── CoverageDecorator.ts
│   ├── api/
│   │   └── ResearchAnalyserClient.ts  — API calls + SSE
│   └── webview/
│       ├── panel.html
│       ├── panel.ts          — webview-side JS
│       └── katex/            — bundled KaTeX assets
├── package.json
├── tsconfig.json
├── esbuild.config.js
└── README.md
```

---

## 12. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-1 | Loading an `analysis_report.json` populates the sidebar within 500 ms |
| AC-2 | Hovering over a known symbol shows the equation card within 200 ms |
| AC-3 | Hovering over an unknown symbol shows nothing (no false positives) |
| AC-4 | Opening `spec.md` renders all `$$...$$` blocks as KaTeX (not raw strings) |
| AC-5 | Equation Picker lists all equations and inserts the selected one at cursor |
| AC-6 | `⇧⌘R` triggers analysis; progress notification updates at least every 5 s |
| AC-7 | If API is offline, extension shows a "Start server?" prompt |
| AC-8 | Coverage sidebar correctly counts `@implements` annotations and shows uncovered sections |
| AC-9 | All KaTeX rendering works fully offline (no CDN requests) |
| AC-10 | Extension activates in < 300 ms on startup (lazy-loads heavy providers) |

---

## 13. Phase Plan

### Phase 1 — Core (MVP)
- [ ] Extension scaffold (`activate`, `package.json`, commands registered)
- [ ] `ReportStore` — load from file or API
- [ ] `ResearchPanel` — Summary + Equations tabs with KaTeX
- [ ] `EquationPickerCommand` — insert equation at cursor
- [ ] `loadReportCommand` — file picker for `analysis_report.json`

### Phase 2 — Intelligence
- [ ] `EquationHoverProvider` — symbol index + hover cards
- [ ] `SpecDocumentProvider` — spec.md custom renderer with KaTeX decorations
- [ ] `analyseCommand` — API call + SSE progress stream
- [ ] Sidebar TreeView (paper, equations, spec sections)

### Phase 3 — Coverage & Polish
- [ ] `CoverageDecorator` — `@implements §X.Y` gutter icons
- [ ] Coverage sidebar with uncovered sections highlighted
- [ ] `markImplementsCommand` with section QuickPick
- [ ] Settings page (`researchAnalyser.*` workspace config)
- [ ] Auto-start API server if not running
- [ ] Publish to VS Code Marketplace + Open VSX
