import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { EquationIndex, EquationRef } from "../types";

export class EquationHoverProvider implements vscode.HoverProvider {
  private _index: EquationIndex | null = null;
  private readonly _store: ReportStore;

  constructor(store: ReportStore) {
    this._store = store;
    this._index = store.getEquationIndex();
    store.onDidChange(() => {
      this._index = store.getEquationIndex();
    });
  }

  provideHover(
    document: vscode.TextDocument,
    position: vscode.Position
  ): vscode.Hover | undefined {
    if (!this._index) { return undefined; }

    const wordRange = document.getWordRangeAtPosition(position, /[a-zA-Z_][a-zA-Z0-9_]*/);
    if (!wordRange) { return undefined; }

    const word = document.getText(wordRange).toLowerCase();
    const refs = this._index.bySymbol.get(word);
    if (!refs || refs.length === 0) { return undefined; }

    const md = this._buildCard(refs[0]);
    return new vscode.Hover(md, wordRange);
  }

  private _buildCard(ref: EquationRef): vscode.MarkdownString {
    const md = new vscode.MarkdownString(undefined, true);
    md.isTrusted = true;
    md.supportHtml = true;
    md.appendMarkdown(`**${ref.label ?? ref.equationId}** · §${ref.section}\n\n`);
    md.appendMarkdown(`<div style="padding:4px 0">${ref.renderedHtml}</div>\n\n`);
    md.appendMarkdown(
      `[Copy LaTeX](command:researchAnalyser.copyEquation?${encodeURIComponent(JSON.stringify([ref.equationId]))})  ` +
      `[Show in Panel](command:researchAnalyser.openPanel)`
    );
    return md;
  }
}
