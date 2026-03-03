import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { FromWebviewMessage, ToWebviewMessage } from "../types";

export class ResearchPanel {
  private static _current: ResearchPanel | undefined;

  private readonly _panel: vscode.WebviewPanel;
  private readonly _store: ReportStore;
  private readonly _extensionUri: vscode.Uri;
  private _disposables: vscode.Disposable[] = [];

  static createOrShow(store: ReportStore, extensionUri: vscode.Uri): void {
    if (ResearchPanel._current) {
      ResearchPanel._current._panel.reveal(vscode.ViewColumn.Two);
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "researchAnalyser.panel",
      "Research Analyser",
      vscode.ViewColumn.Two,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, "out", "webview"),
          vscode.Uri.joinPath(extensionUri, "src", "webview", "katex"),
          vscode.Uri.joinPath(extensionUri, "node_modules", "katex", "dist"),
        ],
      }
    );
    ResearchPanel._current = new ResearchPanel(panel, store, extensionUri);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    store: ReportStore,
    extensionUri: vscode.Uri
  ) {
    this._panel = panel;
    this._store = store;
    this._extensionUri = extensionUri;

    this._panel.webview.html = this._getHtml();

    this._panel.onDidDispose(() => this._dispose(), null, this._disposables);

    this._panel.webview.onDidReceiveMessage(
      (msg: FromWebviewMessage) => this._handleMessage(msg),
      null,
      this._disposables
    );

    store.onDidChange(() => {
      const state = store.state;
      if (state.status === "loaded") {
        this._post({ type: "loadReport", report: state.report });
      } else if (state.status === "empty") {
        this._post({ type: "clearReport" });
      }
    }, null, this._disposables);

    vscode.window.onDidChangeActiveColorTheme(
      (theme) => {
        const kind =
          theme.kind === vscode.ColorThemeKind.Dark
            ? "dark"
            : theme.kind === vscode.ColorThemeKind.HighContrast
            ? "high-contrast"
            : "light";
        this._post({ type: "setTheme", kind });
      },
      null,
      this._disposables
    );
  }

  private _post(msg: ToWebviewMessage): void {
    this._panel.webview.postMessage(msg);
  }

  private _handleMessage(msg: FromWebviewMessage): void {
    switch (msg.type) {
      case "ready": {
        const state = this._store.state;
        if (state.status === "loaded") {
          this._post({ type: "loadReport", report: state.report });
        }
        break;
      }
      case "insertEquation": {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { break; }
        let text: string;
        switch (msg.format) {
          case "comment":
            text = `# ${msg.label ? msg.label + ": " : ""}$$${msg.latex}$$`;
            break;
          case "docstring":
            text = `"""LaTeX: ${msg.latex}"""`;
            break;
          default:
            text = msg.latex;
        }
        editor.edit((eb) => eb.insert(editor.selection.active, text));
        break;
      }
      case "copyEquation":
        vscode.env.clipboard.writeText(msg.latex);
        break;
      case "openExternal":
        vscode.env.openExternal(vscode.Uri.parse(msg.url));
        break;
    }
  }

  private _getHtml(): string {
    const webview = this._panel.webview;
    const panelJsUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "out", "webview", "panel.js")
    );
    const katexCssUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "node_modules", "katex", "dist", "katex.min.css")
    );

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src ${webview.cspSource}; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}"/>
  <link href="${katexCssUri}" rel="stylesheet"/>
  <title>Research Analyser</title>
  <style>
    body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); color: var(--vscode-foreground); background: var(--vscode-editor-background); padding: 0; margin: 0; }
    .tabs { display: flex; border-bottom: 1px solid var(--vscode-panel-border); }
    .tab { padding: 6px 14px; cursor: pointer; border-bottom: 2px solid transparent; }
    .tab.active { border-bottom-color: var(--vscode-focusBorder); }
    .panel { padding: 12px; display: none; }
    .panel.active { display: block; }
    .card { background: var(--vscode-editor-inactiveSelectionBackground); border-radius: 4px; padding: 10px; margin-bottom: 10px; }
    .eq-card { margin-bottom: 14px; border: 1px solid var(--vscode-panel-border); border-radius: 4px; padding: 10px; }
    .eq-actions button { margin-right: 6px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 3px 8px; cursor: pointer; border-radius: 3px; }
    .score-bar { height: 8px; background: var(--vscode-charts-green); border-radius: 4px; }
    .empty-state { text-align: center; padding: 40px; opacity: 0.6; }
  </style>
</head>
<body>
  <div class="tabs" id="tabs">
    <div class="tab active" data-tab="summary">Summary</div>
    <div class="tab" data-tab="equations">Equations</div>
    <div class="tab" data-tab="diagrams">Diagrams</div>
    <div class="tab" data-tab="review">Peer Review</div>
    <div class="tab" data-tab="spec">Spec</div>
  </div>
  <div class="panel active" id="panel-summary"><div class="empty-state">Load a report to get started</div></div>
  <div class="panel" id="panel-equations"></div>
  <div class="panel" id="panel-diagrams"></div>
  <div class="panel" id="panel-review"></div>
  <div class="panel" id="panel-spec"></div>
  <script src="${panelJsUri}"></script>
</body>
</html>`;
  }

  private _dispose(): void {
    ResearchPanel._current = undefined;
    this._panel.dispose();
    this._disposables.forEach((d) => d.dispose());
    this._disposables = [];
  }
}
