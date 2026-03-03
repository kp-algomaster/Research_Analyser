import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { ReportStore } from "./store/ReportStore";
import { ResearchAnalyserClient } from "./api/ResearchAnalyserClient";
import { EquationHoverProvider } from "./providers/EquationHoverProvider";
import { ResearchTreeDataProvider } from "./providers/ResearchTreeDataProvider";
import { SpecDocumentProvider } from "./providers/SpecDocumentProvider";
import { ResearchPanel } from "./panels/ResearchPanel";
import { CoverageDecorator, setExtensionUri } from "./decorators/CoverageDecorator";
import { loadReportCommand } from "./commands/loadReportCommand";
import { pickEquationCommand, copyEquationCommand } from "./commands/pickEquationCommand";
import { analyseCommand } from "./commands/analyseCommand";
import { fetchPaperCommand } from "./commands/fetchPaperCommand";
import { downloadMonkeyOcrCommand } from "./commands/downloadMonkeyOcrCommand";
import { markImplementsCommand } from "./commands/markImplementsCommand";
import { startServerCommand } from "./commands/startServerCommand";
import { textToDiagramsCommand } from "./commands/textToDiagramsCommand";
import { generateReviewCommand } from "./commands/generateReviewCommand";

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  setExtensionUri(context.extensionUri);

  // Core singletons
  const store = ReportStore.getInstance();
  const client = new ResearchAnalyserClient();

  // Health check → context key
  client.health().then((alive) => {
    vscode.commands.executeCommand("setContext", "researchAnalyser.serverRunning", alive);
  });

  // Auto-load latest report
  const config = vscode.workspace.getConfiguration("researchAnalyser");
  if (config.get<boolean>("autoLoadLatestReport", true)) {
    client.getLatestReport().then((report) => {
      if (report) {
        store.load(report, "api:latest");
      }
    }).catch(() => {/* silent — server may not be running */});
  }

  // Providers
  const hoverProvider = new EquationHoverProvider(store);
  const treeProvider = new ResearchTreeDataProvider(store);
  const coverageDecorator = new CoverageDecorator(store);

  coverageDecorator.onDidChange(() => {
    treeProvider.updateCoverage(coverageDecorator.getCoverageItems());
  });

  // Sidebar tree view
  const treeView = vscode.window.createTreeView("researchAnalyser.sidebar", {
    treeDataProvider: treeProvider,
    showCollapseAll: true,
  });

  // Hover provider — register for configured languages
  const hoverLanguages = config.get<string[]>("hoverLanguages", [
    "python", "typescript", "javascript", "cpp", "rust",
  ]);
  const hoverEnabled = config.get<boolean>("hoverEnabled", true);
  const hoverDisposables: vscode.Disposable[] = [];
  if (hoverEnabled) {
    for (const lang of hoverLanguages) {
      hoverDisposables.push(
        vscode.languages.registerHoverProvider(lang, hoverProvider)
      );
    }
  }

  // Spec document provider
  const specProvider = new SpecDocumentProvider(context.extensionUri);
  const specDisposable = vscode.window.registerCustomEditorProvider(
    SpecDocumentProvider.viewType,
    specProvider,
    { webviewOptions: { retainContextWhenHidden: true } }
  );

  // Commands
  const commands: vscode.Disposable[] = [
    vscode.commands.registerCommand("researchAnalyser.analyse", (source?: string) =>
      analyseCommand(store, client, source)
    ),
    vscode.commands.registerCommand("researchAnalyser.loadReport", (uri?: vscode.Uri) =>
      loadReportCommand(store, uri)
    ),
    vscode.commands.registerCommand("researchAnalyser.openPanel", () =>
      ResearchPanel.createOrShow(store, context.extensionUri)
    ),
    vscode.commands.registerCommand("researchAnalyser.pickEquation", () =>
      pickEquationCommand(store)
    ),
    vscode.commands.registerCommand("researchAnalyser.clearReport", () => {
      store.clear();
      vscode.window.showInformationMessage("Report cleared");
    }),
    vscode.commands.registerCommand(
      "researchAnalyser.copyEquation",
      (equationId: string) => copyEquationCommand(store, equationId)
    ),
    vscode.commands.registerCommand("researchAnalyser.markImplements", () =>
      markImplementsCommand(store)
    ),
    vscode.commands.registerCommand("researchAnalyser.fetchPaper", (source?: string) =>
      fetchPaperCommand(store, client, source)
    ),
    vscode.commands.registerCommand("researchAnalyser.downloadMonkeyOcr", () =>
      downloadMonkeyOcrCommand(client, treeProvider)
    ),
    vscode.commands.registerCommand("researchAnalyser.startServer", () =>
      startServerCommand(client)
    ),
    vscode.commands.registerCommand("researchAnalyser.textToDiagrams", () =>
      textToDiagramsCommand(client)
    ),
    vscode.commands.registerCommand("researchAnalyser.generateReview", () =>
      generateReviewCommand(store, client)
    ),
    vscode.commands.registerCommand("researchAnalyser.openSettings", () => {
      vscode.commands.executeCommand(
        "workbench.action.openSettings",
        "@ext:kp-algomaster.research-analyser"
      );
    }),
    vscode.commands.registerCommand("researchAnalyser.saveApiKeys", async () => {
      const cfg = vscode.workspace.getConfiguration("researchAnalyser.keys");
      const keyMap: Record<string, string> = {
        OPENAI_API_KEY:           cfg.get<string>("openai", ""),
        GOOGLE_API_KEY:           cfg.get<string>("google", ""),
        TAVILY_API_KEY:           cfg.get<string>("tavily", ""),
        SEMANTIC_SCHOLAR_API_KEY: cfg.get<string>("semanticScholar", ""),
        HF_TOKEN:                 cfg.get<string>("huggingface", ""),
      };

      // Find workspace root
      const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!wsFolder) {
        vscode.window.showErrorMessage("Research Analyser: No workspace folder open.");
        return;
      }

      const envPath = path.join(wsFolder, ".env");
      let content = "";
      try { content = fs.readFileSync(envPath, "utf8"); } catch { /* new file */ }

      for (const [key, val] of Object.entries(keyMap)) {
        if (!val) { continue; }
        const re = new RegExp(`^${key}=.*$`, "m");
        if (re.test(content)) {
          content = content.replace(re, `${key}=${val}`);
        } else {
          content = content.trimEnd() + `\n${key}=${val}\n`;
        }
      }

      fs.writeFileSync(envPath, content, "utf8");
      const saved = Object.keys(keyMap).filter((k) => keyMap[k]).join(", ");
      vscode.window.showInformationMessage(
        `Research Analyser: Saved ${saved || "no keys (all blank)"} to .env`
      );
    }),
  ];

  // Push all disposables
  context.subscriptions.push(
    ...commands,
    ...hoverDisposables,
    specDisposable,
    treeView,
    coverageDecorator,
    { dispose: () => store.dispose() }
  );
}

export function deactivate(): void {
  // Disposables are cleaned up via context.subscriptions
}
