# Data Model — VS Code Extension: Research Analyser Integration

All types live in `src/types/`. Types that mirror Research Analyser Python models are
prefixed with the section of `models.py` they correspond to.

---

## Core Domain Types

### `AnalysisReport` (mirrors Python `AnalysisReport` dataclass)

```typescript
export interface AnalysisReport {
  extracted_content: ExtractedContent;
  summary: PaperSummary | null;
  review: PeerReview | null;
  diagrams: GeneratedDiagram[];
  key_points: KeyPoint[];
  metadata: ReportMetadata;
  storm_report: string | null;
}

export interface ExtractedContent {
  title: string;
  authors: string[];
  abstract: string;
  sections: Section[];
  equations: Equation[];
  tables: Table[];
  figures: Figure[];
  references: Reference[];
  full_text: string;
}

export interface Section {
  title: string;
  content: string;
  level: number;
  section_number: string;
}

export interface Equation {
  id: string;
  label: string | null;
  latex: string;
  section: string;
  is_inline: boolean;
  description: string | null;
}

export interface PaperSummary {
  one_sentence: string;
  abstract_summary: string;
  methodology_summary: string;
  results_summary: string;
  conclusions: string;
}

export interface PeerReview {
  overall_score: number;
  confidence: number;
  strengths: string[];
  weaknesses: string[];
  dimensions: Record<string, ReviewDimension>;
  decision: string;
}

export interface ReviewDimension {
  name: string;
  score: number;
  comments: string;
}

export interface GeneratedDiagram {
  diagram_type: string;
  image_path: string;
  caption: string;
  source_context: string;
  iterations: number;
  format: string;
  is_fallback: boolean;
  error: string | null;
}

export interface KeyPoint {
  point: string;
  evidence: string;
  section: string;
  importance: "high" | "medium" | "low";
}

export interface ReportMetadata {
  ocr_model: string;
  diagram_provider: string;
  review_model: string;
  processing_time_seconds: number;
  created_at: string; // ISO 8601
}
```

---

## Extension-Internal Types

### `EquationIndex` — built from loaded report

```typescript
/**
 * Maps symbol names to the equations that define them.
 * Built once when a report loads; queried on every hover.
 */
export interface EquationIndex {
  /** symbol (lowercase) → list of equations that contain it */
  bySymbol: Map<string, EquationRef[]>;
  /** equation id → full Equation object */
  byId: Map<string, Equation>;
}

export interface EquationRef {
  equationId: string;
  latex: string;
  label: string | null;
  section: string;
  /** rendered KaTeX HTML for hover display */
  renderedHtml: string;
}
```

### `AnnotationMap` — implementation coverage tracker

```typescript
/**
 * Maps spec section references found in @implements annotations
 * to their file locations in the workspace.
 */
export interface AnnotationMap {
  /** section ref (e.g. "3.2") → list of code locations */
  bySection: Map<string, CodeLocation[]>;
  /** all section refs found in the loaded report */
  reportSections: Set<string>;
}

export interface CodeLocation {
  uri: vscode.Uri;
  range: vscode.Range;
  sectionRef: string; // e.g. "3.2"
  lineText: string;
}
```

### `ReportStoreState`

```typescript
export type ReportStoreState =
  | { status: "empty" }
  | { status: "loading"; source: string }
  | { status: "loaded"; report: AnalysisReport; source: string; loadedAt: Date }
  | { status: "error"; message: string };
```

### `InsertFormat`

```typescript
export type InsertFormat =
  | "comment"     // # $$ latex $$
  | "docstring"   // """LaTeX: latex"""
  | "raw";        // raw LaTeX string
```

### `CoverageItem` — for TreeDataProvider

```typescript
export interface CoverageItem {
  sectionRef: string;         // "3.2"
  sectionTitle: string;       // "View-Adaptive Curve Model"
  implemented: boolean;
  locations: CodeLocation[];  // empty if not implemented
}
```

---

## Webview Message Types

```typescript
// src/types/messages.ts — shared by extension host and webview bundle

export type ToWebviewMessage =
  | { type: "loadReport"; report: AnalysisReport }
  | { type: "scrollToEquation"; id: string }
  | { type: "setTheme"; kind: "dark" | "light" | "high-contrast" }
  | { type: "clearReport" };

export type FromWebviewMessage =
  | { type: "ready" }
  | { type: "insertEquation"; latex: string; label: string | null; format: InsertFormat }
  | { type: "copyEquation"; latex: string }
  | { type: "openExternal"; url: string }
  | { type: "showSection"; sectionRef: string };
```

---

## API Client Types

```typescript
// src/api/types.ts

export interface AnalyseRequest {
  source: string;                  // PDF path, URL, arXiv ID, DOI
  options?: Partial<AnalysisOptions>;
}

export interface AnalysisOptions {
  generate_diagrams: boolean;
  generate_review: boolean;
  generate_storm_report: boolean;
  generate_audio: boolean;
  diagram_types: string[];
}

export interface ProgressEvent {
  pct: number;       // 0–100
  message: string;
}

export type AnalyseStreamEvent =
  | { event: "progress"; data: ProgressEvent }
  | { event: "complete"; data: AnalysisReport }
  | { event: "error"; data: { message: string } };
```

---

## State Transitions

```
ReportStoreState:

  empty ──[load(source)]──► loading
  loading ──[success]──► loaded
  loading ──[failure]──► error
  error ──[load(source)]──► loading
  loaded ──[clear()]──► empty
  loaded ──[load(source)]──► loading   (replace report)
```

```
Analysis flow:

  idle ──[analyseCommand]──► streaming progress
  streaming ──[SSE complete]──► ReportStore.loaded
  streaming ──[SSE error]──► notification + idle
  streaming ──[user cancel]──► idle
```

---

## Validation Rules

| Field | Rule |
|-------|------|
| `Equation.latex` | Must be non-empty; stripped of leading/trailing whitespace |
| `Equation.id` | Unique within report; format `eq-N` or arbitrary string |
| `AnalysisReport` | `extracted_content` required; all other fields nullable |
| `AnnotationMap.bySection` key | Regex `^\d+(\.\d+)*$` (e.g. "3", "3.2", "3.2.1") |
| `ProgressEvent.pct` | Integer 0–100 inclusive |
