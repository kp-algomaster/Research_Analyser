import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";

function getCommentPrefix(languageId: string): string {
  const map: Record<string, string> = {
    python: "#",
    ruby: "#",
    shellscript: "#",
    typescript: "//",
    javascript: "//",
    java: "//",
    cpp: "//",
    c: "//",
    rust: "//",
    go: "//",
    kotlin: "//",
    swift: "//",
    lua: "--",
    sql: "--",
    haskell: "--",
  };
  return map[languageId] ?? "//";
}

export async function markImplementsCommand(store: ReportStore): Promise<void> {
  const report = store.report;
  if (!report) {
    vscode.window.showWarningMessage("No report loaded.");
    return;
  }

  const sections = report.extracted_content.sections;
  if (sections.length === 0) {
    vscode.window.showInformationMessage("No sections found in the loaded report.");
    return;
  }

  const items: vscode.QuickPickItem[] = sections.map((s) => ({
    label: `§${s.section_number}`,
    description: s.title,
  }));

  const chosen = await vscode.window.showQuickPick(items, {
    placeHolder: "Select spec section this code implements",
    matchOnDescription: true,
  });
  if (!chosen) { return; }

  const section = sections[items.indexOf(chosen)];
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor.");
    return;
  }

  const prefix = getCommentPrefix(editor.document.languageId);
  const annotation = `${prefix} @implements §${section.section_number} — ${section.title}`;

  await editor.edit((eb) => {
    const line = editor.selection.active.line;
    eb.insert(new vscode.Position(line, 0), annotation + "\n");
  });
}
