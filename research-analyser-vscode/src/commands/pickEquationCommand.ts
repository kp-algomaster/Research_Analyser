import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { InsertFormat } from "../types";

function formatEquation(latex: string, label: string | null, format: InsertFormat): string {
  switch (format) {
    case "comment":
      return `# ${label ? label + ": " : ""}$$${latex}$$`;
    case "docstring":
      return `"""LaTeX${label ? " " + label : ""}: ${latex}"""`;
    case "raw":
    default:
      return latex;
  }
}

export async function pickEquationCommand(store: ReportStore): Promise<void> {
  const report = store.report;
  if (!report) {
    vscode.window.showWarningMessage("No report loaded. Use ⇧⌘R to analyse a paper first.");
    return;
  }

  const equations = report.extracted_content.equations;
  if (equations.length === 0) {
    vscode.window.showInformationMessage("No equations found in the loaded report.");
    return;
  }

  const items: vscode.QuickPickItem[] = equations.map((eq) => ({
    label: `$(symbol-operator) ${eq.label ?? eq.id} · §${eq.section}`,
    description: eq.latex.substring(0, 80),
    detail: eq.description ?? undefined,
  }));

  const chosen = await vscode.window.showQuickPick(items, {
    placeHolder: "Select an equation to insert",
    matchOnDescription: true,
  });
  if (!chosen) { return; }

  const idx = items.indexOf(chosen);
  const eq = equations[idx];

  const formatItems: vscode.QuickPickItem[] = [
    { label: "comment", description: "# $$latex$$ — language comment" },
    { label: "docstring", description: '"""LaTeX: ...""" — Python docstring style' },
    { label: "raw", description: "raw LaTeX string" },
  ];

  const defaultFmt = vscode.workspace
    .getConfiguration("researchAnalyser")
    .get<InsertFormat>("insertFormat", "comment");

  const quickPick = vscode.window.createQuickPick();
  quickPick.items = formatItems;
  quickPick.placeholder = "Choose insertion format";
  quickPick.activeItems = formatItems.filter((i) => i.label === defaultFmt);

  const fmtChosen = await new Promise<vscode.QuickPickItem | undefined>((resolve) => {
    quickPick.onDidAccept(() => { resolve(quickPick.activeItems[0]); quickPick.dispose(); });
    quickPick.onDidHide(() => { resolve(undefined); quickPick.dispose(); });
    quickPick.show();
  });
  if (!fmtChosen) { return; }

  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor to insert into.");
    return;
  }

  const text = formatEquation(eq.latex, eq.label, fmtChosen.label as InsertFormat);
  await editor.edit((editBuilder) => {
    editBuilder.insert(editor.selection.active, text);
  });
}

export async function copyEquationCommand(store: ReportStore, equationId: string): Promise<void> {
  const report = store.report;
  if (!report) { return; }
  const eq = report.extracted_content.equations.find((e) => e.id === equationId);
  if (!eq) { return; }
  await vscode.env.clipboard.writeText(eq.latex);
  vscode.window.showInformationMessage("Copied to clipboard");
}
