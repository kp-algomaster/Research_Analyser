import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { AnnotationMap, CodeLocation, CoverageItem } from "../types";

const IMPLEMENTS_RE = /@implements\s+§(\d+(?:\.\d+)*)/g;

export class CoverageDecorator {
  private _annotationMap: AnnotationMap = {
    bySection: new Map(),
    reportSections: new Set(),
  };

  private readonly _coveredType: vscode.TextEditorDecorationType;
  private readonly _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChange = this._onDidChange.event;

  private _disposables: vscode.Disposable[] = [];

  constructor(private readonly _store: ReportStore) {
    this._coveredType = vscode.window.createTextEditorDecorationType({
      gutterIconPath: vscode.Uri.joinPath(
        getExtensionUri(),
        "src",
        "assets",
        "covered.svg"
      ),
      gutterIconSize: "75%",
    });

    _store.onDidChange(() => {
      const report = _store.report;
      if (report) {
        this._annotationMap.reportSections = new Set(
          report.extracted_content.sections.map((s) => s.section_number)
        );
      } else {
        this._annotationMap.reportSections = new Set();
        this._annotationMap.bySection = new Map();
        this._onDidChange.fire();
        return;
      }
      this._scan().then(() => this._onDidChange.fire());
    }, null, this._disposables);

    vscode.workspace.onDidSaveTextDocument(
      () => this._scan().then(() => this._onDidChange.fire()),
      null,
      this._disposables
    );

    vscode.window.onDidChangeActiveTextEditor(
      (editor) => {
        if (editor) { this._applyDecorations(editor); }
      },
      null,
      this._disposables
    );
  }

  getAnnotationMap(): AnnotationMap {
    return this._annotationMap;
  }

  getCoverageItems(): CoverageItem[] {
    const report = this._store.report;
    if (!report) { return []; }
    return report.extracted_content.sections.map((s) => ({
      sectionRef: s.section_number,
      sectionTitle: s.title,
      implemented: this._annotationMap.bySection.has(s.section_number),
      locations: this._annotationMap.bySection.get(s.section_number) ?? [],
    }));
  }

  private async _scan(): Promise<void> {
    const files = await vscode.workspace.findFiles(
      "**/*.{ts,js,py,rs,go,cpp,java,kt,swift}",
      "**/node_modules/**"
    );
    const bySection = new Map<string, CodeLocation[]>();

    for (const fileUri of files) {
      try {
        const doc = await vscode.workspace.openTextDocument(fileUri);
        for (let i = 0; i < doc.lineCount; i++) {
          const line = doc.lineAt(i);
          const re = new RegExp(IMPLEMENTS_RE.source, "g");
          let m: RegExpExecArray | null;
          while ((m = re.exec(line.text)) !== null) {
            const ref = m[1];
            if (!bySection.has(ref)) { bySection.set(ref, []); }
            bySection.get(ref)!.push({
              uri: fileUri,
              range: new vscode.Range(i, m.index, i, m.index + m[0].length),
              sectionRef: ref,
              lineText: line.text.trim(),
            });
          }
        }
      } catch {
        // skip unreadable files
      }
    }

    this._annotationMap = { bySection, reportSections: this._annotationMap.reportSections };
    this._applyDecorationsToAll();
  }

  private _applyDecorationsToAll(): void {
    for (const editor of vscode.window.visibleTextEditors) {
      this._applyDecorations(editor);
    }
  }

  private _applyDecorations(editor: vscode.TextEditor): void {
    const ranges: vscode.DecorationOptions[] = [];
    for (const [, locations] of this._annotationMap.bySection) {
      for (const loc of locations) {
        if (loc.uri.toString() === editor.document.uri.toString()) {
          ranges.push({ range: loc.range });
        }
      }
    }
    editor.setDecorations(this._coveredType, ranges);
  }

  dispose(): void {
    this._coveredType.dispose();
    this._onDidChange.dispose();
    this._disposables.forEach((d) => d.dispose());
  }
}

// Helper to get extension URI — set from activate()
let _extUri: vscode.Uri = vscode.Uri.file("");
export function setExtensionUri(uri: vscode.Uri): void {
  _extUri = uri;
}
function getExtensionUri(): vscode.Uri {
  return _extUri;
}
