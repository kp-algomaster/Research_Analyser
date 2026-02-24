# Contract: Webview ↔ Extension Message Protocol

All communication between the extension host (Node.js) and the WebviewPanel / CustomTextEditorProvider
(browser sandbox) uses `postMessage` / `onDidReceiveMessage`.

Messages are **typed discriminated unions** defined in `src/types/messages.ts` and imported
by both the extension bundle and the webview bundle.

---

## Extension → Webview (`ToWebviewMessage`)

### `loadReport`
```typescript
{ type: "loadReport"; report: AnalysisReport }
```
Sent when `ReportStore` loads a new report. Webview re-renders all tabs.

### `scrollToEquation`
```typescript
{ type: "scrollToEquation"; id: string }
```
Sent when user clicks an equation in the sidebar TreeView. Webview scrolls its Equations tab to the matching card.

### `setTheme`
```typescript
{ type: "setTheme"; kind: "dark" | "light" | "high-contrast" }
```
Sent on `vscode.window.onDidChangeActiveColorTheme`. Webview updates KaTeX CSS.

### `clearReport`
```typescript
{ type: "clearReport" }
```
Sent when `ReportStore.clear()` is called. Webview shows empty state.

---

## Webview → Extension (`FromWebviewMessage`)

### `ready`
```typescript
{ type: "ready" }
```
Sent once when the webview HTML has loaded and is ready to receive messages. Extension responds with `loadReport` if a report is loaded.

### `insertEquation`
```typescript
{ type: "insertEquation"; latex: string; label: string | null; format: InsertFormat }
```
Sent when user clicks "Insert" on an equation card. Extension inserts the equation at the active editor cursor.

**Format values**:
- `"comment"` → `# $$\latex$$` (language-appropriate comment)
- `"docstring"` → `"""LaTeX: \latex"""`
- `"raw"` → bare LaTeX string

### `copyEquation`
```typescript
{ type: "copyEquation"; latex: string }
```
Sent when user clicks "Copy LaTeX" on an equation card. Extension writes to system clipboard.

### `openExternal`
```typescript
{ type: "openExternal"; url: string }
```
Sent for any external link in the webview (e.g. arXiv link). Extension calls `vscode.env.openExternal`.

### `showSection`
```typescript
{ type: "showSection"; sectionRef: string }
```
Sent when user clicks a spec section link. Extension reveals the section in the sidebar coverage tree.

---

## Sequence: Initial Load

```
Extension host                     Webview
     |                                |
     |── create WebviewPanel ─────────►
     |                                |← "ready"
     |── loadReport(report) ─────────►
     |                                |  [renders tabs]
     |                                |
```

## Sequence: Insert Equation

```
User clicks "Insert" in webview
     |                                |
     |◄─ insertEquation(latex) ───────|
     |                                |
 [insert at cursor]                   |
     |── (no response needed) ───────►
```

---

## Serialisation Rules

- All messages serialised as JSON via `postMessage`
- `AnalysisReport` diagram paths (`image_path`) are absolute local paths;
  webview must convert to `vscode.Uri.file(path)` → `webview.asWebviewUri()` before use in `<img src>`
- Dates serialised as ISO 8601 strings
- No `undefined` values in messages — use `null` instead (JSON safe)
