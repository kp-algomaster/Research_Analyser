import * as vscode from "vscode";
import { renderToString, renderInline } from "../util/latexRenderer";

export class SpecDocumentProvider implements vscode.CustomTextEditorProvider {
  static readonly viewType = "researchAnalyser.specRenderer";

  private readonly _extensionUri: vscode.Uri;

  constructor(extensionUri: vscode.Uri) {
    this._extensionUri = extensionUri;
  }

  async resolveCustomTextEditor(
    document: vscode.TextDocument,
    webviewPanel: vscode.WebviewPanel,
    _token: vscode.CancellationToken
  ): Promise<void> {
    webviewPanel.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this._extensionUri, "node_modules", "katex", "dist"),
      ],
    };

    const katexCssUri = webviewPanel.webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "node_modules", "katex", "dist", "katex.min.css")
    );

    const render = () => {
      webviewPanel.webview.html = this._buildHtml(document.getText(), katexCssUri);
    };

    render();

    const listener = vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.uri.toString() === document.uri.toString()) {
        render();
      }
    });

    webviewPanel.onDidDispose(() => listener.dispose());
  }

  private _buildHtml(markdown: string, katexCssUri: vscode.Uri): string {
    const rendered = this._renderMarkdown(markdown);
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src data:; font-src *;"/>
  <link href="${katexCssUri}" rel="stylesheet"/>
  <style>
    body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); color: var(--vscode-foreground); background: var(--vscode-editor-background); padding: 16px; line-height: 1.6; }
    h1,h2,h3 { color: var(--vscode-foreground); }
    code { background: var(--vscode-textCodeBlock-background); padding: 2px 4px; border-radius: 3px; }
    pre { background: var(--vscode-textCodeBlock-background); padding: 12px; border-radius: 4px; overflow: auto; }
    .katex-display { margin: 16px 0; }
  </style>
</head>
<body>${rendered}</body>
</html>`;
  }

  private _renderMarkdown(text: string): string {
    // Replace $$...$$ display math
    let html = text.replace(/\$\$([\s\S]+?)\$\$/g, (_m, latex: string) => {
      return renderToString(latex);
    });
    // Replace $...$ inline math
    html = html.replace(/\$([^$\n]+?)\$/g, (_m, latex: string) => {
      return renderInline(latex);
    });
    // Basic markdown: headings, bold, italic, code blocks, paragraphs
    html = html
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\n\n/g, "</p><p>")
      .replace(/^/, "<p>")
      .replace(/$/, "</p>");
    return html;
  }
}
