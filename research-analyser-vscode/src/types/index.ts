import * as vscode from "vscode";

// ---------------------------------------------------------------------------
// Core domain types (mirror Python AnalysisReport dataclasses)
// ---------------------------------------------------------------------------

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

export interface Table {
  id: string;
  caption: string | null;
  content: string;
}

export interface Figure {
  id: string;
  caption: string | null;
  image_path: string | null;
}

export interface Reference {
  id: string;
  text: string;
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

// ---------------------------------------------------------------------------
// Extension-internal types
// ---------------------------------------------------------------------------

export interface EquationIndex {
  bySymbol: Map<string, EquationRef[]>;
  byId: Map<string, Equation>;
}

export interface EquationRef {
  equationId: string;
  latex: string;
  label: string | null;
  section: string;
  renderedHtml: string;
}

export interface AnnotationMap {
  bySection: Map<string, CodeLocation[]>;
  reportSections: Set<string>;
}

export interface CodeLocation {
  uri: vscode.Uri;
  range: vscode.Range;
  sectionRef: string;
  lineText: string;
}

export type ReportStoreState =
  | { status: "empty" }
  | { status: "loading"; source: string }
  | { status: "loaded"; report: AnalysisReport; source: string; loadedAt: Date }
  | { status: "error"; message: string };

export type InsertFormat = "comment" | "docstring" | "raw";

export interface CoverageItem {
  sectionRef: string;
  sectionTitle: string;
  implemented: boolean;
  locations: CodeLocation[];
}

// ---------------------------------------------------------------------------
// Webview message types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// API client types
// ---------------------------------------------------------------------------

export interface AnalyseRequest {
  source: string;
  options?: Partial<AnalysisOptions>;
}

export interface AnalysisOptions {
  generate_diagrams: boolean;
  generate_review: boolean;
  generate_storm_report: boolean;
  generate_audio: boolean;
  diagram_types: string[];
  diagram_engine: string;
}

export interface ProgressEvent {
  pct: number; // 0–100
  message: string;
}

export type AnalyseStreamEvent =
  | { event: "progress"; data: ProgressEvent }
  | { event: "complete"; data: AnalysisReport }
  | { event: "error"; data: { message: string } };
