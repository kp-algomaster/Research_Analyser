import * as vscode from "vscode";
import * as fs from "fs";
import { ReportStore } from "../store/ReportStore";
import { AnalysisReport } from "../types";

export async function loadReportCommand(store: ReportStore, uri?: vscode.Uri): Promise<void> {
  let targetUri = uri;
  if (!targetUri) {
    const picked = await vscode.window.showOpenDialog({
      filters: { "Analysis Report JSON": ["json"] },
      canSelectMany: false,
      openLabel: "Load Report",
      title: "Select analysis_report.json",
    });
    if (!picked || picked.length === 0) { return; }
    targetUri = picked[0];
  }

  try {
    const raw = fs.readFileSync(targetUri.fsPath, "utf8");
    const report = JSON.parse(raw) as AnalysisReport;
    if (!report.extracted_content) {
      vscode.window.showErrorMessage("Not a valid analysis_report.json");
      return;
    }
    store.load(report, targetUri.fsPath);
    const eq = report.extracted_content.equations.length;
    const title = report.extracted_content.title || "Untitled";
    vscode.window.showInformationMessage(`Loaded: ${title} · ${eq} equations`);
  } catch (e) {
    vscode.window.showErrorMessage(`Failed to load report: ${(e as Error).message}`);
  }
}
