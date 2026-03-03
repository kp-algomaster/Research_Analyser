# Research Analyser — VS Code Extension

Surfaces [Research Analyser](https://github.com/kp-algomaster/Research_Analyser) output — equations, methodology, peer-review scores, and implementation coverage — directly in VS Code.

## Features

| Feature | Shortcut |
|---------|----------|
| Analyse a paper (PDF / URL / arXiv ID) with live SSE progress | `⇧⌘R` |
| Open full report panel (Summary / Equations / Diagrams / Review / Spec tabs) | `⇧⌘E` |
| Insert any equation at cursor (comment / docstring / raw) | `⇧⌘Q` |
| Hover over a symbol to see its LaTeX definition | auto |
| Open `spec.md` → KaTeX-rendered preview (offline, no CDN) | open file |
| Track `@implements §X.Y` annotations in sidebar | auto |

## Requirements

- **Research Analyser** backend running at `http://localhost:8000`
  ```bash
  uvicorn research_analyser.api:app --host 0.0.0.0 --port 8000
  ```
- VS Code **1.85** or later

## Installation

```bash
code --install-extension research-analyser-0.1.0.vsix
```

Or install from source:
```bash
npm ci
npm run build
vsce package
code --install-extension research-analyser-0.1.0.vsix
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `researchAnalyser.apiUrl` | `http://localhost:8000` | Backend URL |
| `researchAnalyser.autoLoadLatestReport` | `true` | Auto-load latest report on activation |
| `researchAnalyser.hoverEnabled` | `true` | Enable equation hover cards |
| `researchAnalyser.hoverLanguages` | `["python","typescript","javascript","cpp","rust"]` | Languages with hover |
| `researchAnalyser.insertFormat` | `"comment"` | Default equation insert format |
| `researchAnalyser.specFileGlob` | `**/{spec,*_spec}.md` | Files opened with KaTeX renderer |

## Usage

### Analyse a Paper

Press `⇧⌘R`, enter an arXiv ID, URL, DOI, or local PDF path. A progress notification streams updates. The report panel opens on completion.

### Load a Saved Report

Run **Research Analyser: Load Report JSON** from the Command Palette and pick an `analysis_report.json` file.

### Insert an Equation

With a file open, press `⇧⌘Q`. Select an equation from the list, then choose the format:
- **comment** → `# label: $$latex$$`
- **docstring** → `"""LaTeX: latex"""`
- **raw** → bare LaTeX

### Hover over Symbols

With a report loaded, hover over any recognised symbol (e.g. `alpha`, `W_q`) in Python/TypeScript/etc. files to see the defining equation rendered via KaTeX.

### Mark Implements

Run **Research Analyser: Mark as Implements §…** to insert an annotation at the cursor:
```python
# @implements §3.2 — View-Adaptive Curve Model
```

The sidebar shows which spec sections are covered (✓) or uncovered (○).

## Development

```bash
npm ci
npm run build   # build extension + webview bundles
npm run watch   # incremental watch mode
npm run lint    # ESLint
npm test        # unit + integration tests
```

Press `F5` in VS Code to launch the Extension Development Host.

## Architecture

```
Extension Host (Node.js)              Webview (browser sandbox)
─────────────────────────────────     ─────────────────────────
extension.ts (activate)               panel.ts (webview JS)
  ├── ReportStore (singleton)    ←──── postMessage ────────────►
  ├── ResearchAnalyserClient           KaTeX rendering
  ├── EquationHoverProvider            Tab UI (Summary/Eqs/…)
  ├── ResearchTreeDataProvider
  ├── SpecDocumentProvider
  ├── ResearchPanel
  └── CoverageDecorator
         │
         ▼
  Research Analyser API (localhost:8000)
```

## License

MIT
