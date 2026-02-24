# Contract: VS Code Command Registry

All commands are registered in `activate()` via `vscode.commands.registerCommand`.
Command IDs follow the `researchAnalyser.<verb><Noun>` convention.

---

## Commands

### `researchAnalyser.analyse`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Analyse Paper |
| **Keybinding** | `⇧⌘R` (Mac) / `Ctrl+Shift+R` (Win/Linux) |
| **When** | always (global) |
| **Args** | `source?: string` — if omitted, shows InputBox |

**Flow**:
1. If `source` not provided → `vscode.window.showInputBox({ prompt: "PDF path, URL, arXiv ID, or DOI" })`
2. Show progress notification: `vscode.window.withProgress`
3. `POST /analyse` with SSE stream → update progress
4. On complete → `ReportStore.load(report)` → open `ResearchPanel`
5. On error → `vscode.window.showErrorMessage`

**Preconditions**: API reachable at `researchAnalyser.apiUrl`; if not → prompt "Start server?"

---

### `researchAnalyser.loadReport`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Load Report JSON |
| **Keybinding** | — |
| **Args** | `uri?: vscode.Uri` — if omitted, shows file picker |

**Flow**:
1. `vscode.window.showOpenDialog({ filters: { JSON: ["json"] } })`
2. Read file → `JSON.parse` → validate against `AnalysisReport` schema
3. `ReportStore.load(report)` → refresh all providers
4. Toast: "Loaded: {paper.title} · {equations.length} equations"

**Error states**: Invalid JSON → `showErrorMessage("Not a valid analysis_report.json")`

---

### `researchAnalyser.openPanel`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Open Report Panel |
| **Keybinding** | `⇧⌘E` (Mac) / `Ctrl+Shift+E` (Win/Linux) |
| **Args** | none |

**Flow**: Create or reveal `ResearchPanel` WebviewPanel. If `ReportStore` is empty → show empty-state panel with "Load a report" CTA.

---

### `researchAnalyser.pickEquation`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Insert Equation |
| **Keybinding** | `⇧⌘Q` (Mac) / `Ctrl+Shift+Q` (Win/Linux) |
| **When** | `editorIsOpen` |
| **Args** | none |

**Flow**:
1. If `ReportStore` empty → show warning "No report loaded"
2. Build `QuickPickItem[]` from `report.equations` (display-only equations first)
3. User selects equation
4. Secondary pick: insert format (`comment` / `docstring` / `raw`)
5. Insert at current cursor position in active editor

**QuickPickItem format**:
```
$(symbol-class) eq-3 · §3 Method
  $\mathcal{L} = \lambda_1 \mathcal{L}_{photo} + ...$
```

---

### `researchAnalyser.clearReport`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Clear Loaded Report |
| **When** | `researchAnalyser.reportLoaded` context key is true |

**Flow**: `ReportStore.clear()` → all providers refresh to empty state → toast "Report cleared"

---

### `researchAnalyser.copyEquation`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Copy Equation (LaTeX) |
| **When** | Context menu in ResearchPanel or equation tree node |
| **Args** | `equationId: string` |

**Flow**: Write `equation.latex` to clipboard → toast "Copied to clipboard"

---

### `researchAnalyser.markImplements`

| Field | Value |
|-------|-------|
| **Title** | Research Analyser: Mark as Implements §… |
| **When** | `editorIsOpen` |
| **Args** | none |

**Flow**:
1. If no report loaded → warning
2. QuickPick from `report.sections` → user selects section
3. Detect comment style for current file language (`#`, `//`, `--`, etc.)
4. Insert `{comment} @implements §{sectionRef} — {sectionTitle}` at cursor line

---

## Context Keys (for `when` clauses)

| Key | Type | Set when |
|-----|------|----------|
| `researchAnalyser.reportLoaded` | boolean | `ReportStore.status === "loaded"` |
| `researchAnalyser.serverRunning` | boolean | `GET /health` returns 200 |

---

## Menu Contributions

```json
"menus": {
  "editor/context": [
    {
      "command": "researchAnalyser.pickEquation",
      "group": "researchAnalyser@1",
      "when": "editorIsOpen && researchAnalyser.reportLoaded"
    },
    {
      "command": "researchAnalyser.markImplements",
      "group": "researchAnalyser@2",
      "when": "editorIsOpen && researchAnalyser.reportLoaded"
    }
  ],
  "view/item/context": [
    {
      "command": "researchAnalyser.copyEquation",
      "when": "viewItem == equation"
    }
  ]
}
```
