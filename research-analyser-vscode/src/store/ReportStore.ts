import * as vscode from "vscode";
import { AnalysisReport, EquationIndex, EquationRef, ReportStoreState } from "../types";
import { buildSymbolIndex } from "../util/symbolIndex";
import { renderToString } from "../util/latexRenderer";

type ChangeListener = () => void;

export class ReportStore {
  private static _instance: ReportStore | undefined;

  private _state: ReportStoreState = { status: "empty" };
  private _equationIndex: EquationIndex | null = null;
  private _listeners: ChangeListener[] = [];

  private readonly _onDidChange = new vscode.EventEmitter<ReportStoreState>();
  readonly onDidChange = this._onDidChange.event;

  private constructor() {}

  static getInstance(): ReportStore {
    if (!ReportStore._instance) {
      ReportStore._instance = new ReportStore();
    }
    return ReportStore._instance;
  }

  get state(): ReportStoreState {
    return this._state;
  }

  get report(): AnalysisReport | null {
    return this._state.status === "loaded" ? this._state.report : null;
  }

  load(report: AnalysisReport, source = "unknown"): void {
    this._state = { status: "loaded", report, source, loadedAt: new Date() };
    this._equationIndex = this._buildIndex(report);
    this._onDidChange.fire(this._state);
    vscode.commands.executeCommand("setContext", "researchAnalyser.reportLoaded", true);
  }

  setLoading(source: string): void {
    this._state = { status: "loading", source };
    this._onDidChange.fire(this._state);
  }

  setError(message: string): void {
    this._state = { status: "error", message };
    this._onDidChange.fire(this._state);
    vscode.commands.executeCommand("setContext", "researchAnalyser.reportLoaded", false);
  }

  clear(): void {
    this._state = { status: "empty" };
    this._equationIndex = null;
    this._onDidChange.fire(this._state);
    vscode.commands.executeCommand("setContext", "researchAnalyser.reportLoaded", false);
  }

  getEquationIndex(): EquationIndex | null {
    return this._equationIndex;
  }

  private _buildIndex(report: AnalysisReport): EquationIndex {
    const refs: EquationRef[] = report.extracted_content.equations.map((eq) => ({
      equationId: eq.id,
      latex: eq.latex,
      label: eq.label,
      section: eq.section,
      renderedHtml: renderToString(eq.latex),
    }));
    return buildSymbolIndex(report.extracted_content.equations, refs);
  }

  dispose(): void {
    this._onDidChange.dispose();
    ReportStore._instance = undefined;
  }
}
