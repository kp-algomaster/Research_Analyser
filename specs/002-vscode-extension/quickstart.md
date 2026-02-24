# Quickstart: VS Code Extension Dev Setup

**Feature**: `002-vscode-extension` | **Date**: 2026-02-24

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 20 LTS | `brew install node` |
| npm | ≥ 10 | bundled with Node |
| TypeScript | 5.4+ | `npm install -g typescript` |
| VS Code | 1.85+ | https://code.visualstudio.com |
| `vsce` | latest | `npm install -g @vscode/vsce` |
| Research Analyser API | running | `uvicorn research_analyser.api:app` |

---

## 1. Create the Extension Repository

```bash
# Create alongside Research_Analyser repo
mkdir research-analyser-vscode
cd research-analyser-vscode
git init
git checkout -b main
```

---

## 2. Scaffold `package.json`

```bash
npm init -y
```

Then replace `package.json` with the extension manifest (see [spec.md §3](spec.md#3-extension-manifest-packagejson-highlights) for full manifest). Key fields:

```json
{
  "name": "research-analyser",
  "displayName": "Research Analyser",
  "publisher": "kp-algomaster",
  "version": "0.1.0",
  "engines": { "vscode": "^1.85.0" },
  "main": "./out/extension.js",
  "activationEvents": ["onStartupFinished"],
  "scripts": {
    "build": "node esbuild.config.js",
    "watch": "node esbuild.config.js --watch",
    "test": "node ./out/test/runTest.js",
    "lint": "eslint src --ext ts",
    "package": "vsce package"
  }
}
```

---

## 3. Install Dependencies

```bash
# Runtime (bundled into extension)
npm install --save-dev \
  @types/vscode@^1.85.0 \
  @types/node@^20 \
  typescript@^5.4 \
  esbuild@^0.21 \
  eslint@^8 \
  @typescript-eslint/eslint-plugin \
  @typescript-eslint/parser

# KaTeX (bundled offline)
npm install katex@^0.16

# Testing
npm install --save-dev \
  @vscode/test-electron@^2 \
  mocha@^10 \
  sinon@^17 \
  @types/mocha \
  @types/sinon
```

---

## 4. Configure TypeScript

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2020",
    "lib": ["ES2020"],
    "outDir": "out",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "declaration": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "out"]
}
```

---

## 5. Configure esbuild

`esbuild.config.js`:
```js
const { build } = require("esbuild");
const watch = process.argv.includes("--watch");

// Extension host bundle (Node.js)
build({
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "out/extension.js",
  external: ["vscode"],
  platform: "node",
  target: "node20",
  sourcemap: true,
  minify: process.env.NODE_ENV === "production",
  watch: watch ? { onRebuild(err) { console.log(err ? "⚠ rebuild error" : "✓ rebuilt"); } } : false,
});

// Webview bundle (browser)
build({
  entryPoints: ["src/webview/panel.ts"],
  bundle: true,
  outfile: "out/webview/panel.js",
  platform: "browser",
  target: ["chrome114"],
  sourcemap: true,
  minify: process.env.NODE_ENV === "production",
  watch: watch ? { onRebuild(err) { console.log(err ? "⚠ webview rebuild error" : "✓ webview rebuilt"); } } : false,
});
```

---

## 6. Create Source Directory Structure

```bash
mkdir -p src/{store,providers,panels,commands,decorators,api,util,webview/katex}
mkdir -p tests/{unit,integration}
```

Matches the structure in [plan.md](plan.md#project-structure):
```
src/
├── extension.ts
├── store/ReportStore.ts
├── providers/{EquationHoverProvider,SpecDocumentProvider,ResearchTreeDataProvider}.ts
├── panels/ResearchPanel.ts
├── commands/{analyseCommand,pickEquationCommand,loadReportCommand,markImplementsCommand}.ts
├── decorators/CoverageDecorator.ts
├── api/ResearchAnalyserClient.ts
├── util/{symbolIndex,latexRenderer}.ts
└── webview/{panel.html,panel.ts,katex/}
```

---

## 7. Bundle KaTeX Assets

```bash
# Copy KaTeX fonts + CSS from node_modules into the webview bundle location
cp -r node_modules/katex/dist/fonts src/webview/katex/
cp node_modules/katex/dist/katex.min.css src/webview/katex/
cp node_modules/katex/dist/katex.min.js src/webview/katex/
```

In webview HTML, reference via `vscode-resource:` URI (set in `ResearchPanel.ts`):
```html
<link rel="stylesheet" href="${katexUri}/katex.min.css">
<script src="${katexUri}/katex.min.js"></script>
```

---

## 8. First Build

```bash
npm run build
# Expected output:
#   ✓ rebuilt  (extension.js)
#   ✓ webview rebuilt  (panel.js)
```

---

## 9. Run in VS Code (F5 Launch)

`.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run Extension",
      "type": "extensionHost",
      "request": "launch",
      "args": ["--extensionDevelopmentPath=${workspaceFolder}"],
      "outFiles": ["${workspaceFolder}/out/**/*.js"],
      "preLaunchTask": "npm: build"
    }
  ]
}
```

Press **F5** to open an Extension Development Host window with the extension loaded.

---

## 10. Run Tests

```bash
npm test
# Runs unit tests (no VS Code needed) + integration tests via @vscode/test-electron
```

Unit tests only (fast, no VS Code binary):
```bash
npx mocha --require ts-node/register 'tests/unit/**/*.test.ts'
```

---

## 11. Connect to Research Analyser API

Ensure the Research Analyser backend is running:
```bash
# From the Research_Analyser project directory
uvicorn research_analyser.api:app --reload
# → http://localhost:8000
```

The extension reads `researchAnalyser.apiUrl` (default `http://localhost:8000`) from VS Code settings.

Test the connection via the health endpoint:
```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

## 12. Package the Extension

```bash
npm run package
# → research-analyser-0.1.0.vsix
```

Install locally:
```bash
code --install-extension research-analyser-0.1.0.vsix
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `vscode module not found` | Ensure `"vscode"` is in `external` in esbuild config |
| KaTeX fonts 404 in webview | Check `vscode-resource:` URI prefix in webview HTML |
| `Cannot reach Research Analyser at http://localhost:8000` | Start the API: `uvicorn research_analyser.api:app` |
| Hover not showing | Check `researchAnalyser.hoverEnabled` is `true`; ensure a report is loaded |
| Extension not activating | Open a markdown file or run any `researchAnalyser.*` command to trigger activation |
