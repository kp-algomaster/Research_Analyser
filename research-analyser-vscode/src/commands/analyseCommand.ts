import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { ResearchAnalyserClient } from "../api/ResearchAnalyserClient";

export async function analyseCommand(
  store: ReportStore,
  client: ResearchAnalyserClient,
  source?: string
): Promise<void> {
  let src = source;
  if (!src) {
    src = await vscode.window.showInputBox({
      prompt: "Enter PDF path, URL, arXiv ID, or DOI",
      placeHolder: "e.g. 2405.12345 or https://arxiv.org/abs/2405.12345",
    });
    if (!src) { return; }
  }

  // Health check
  const alive = await client.health();
  if (!alive) {
    const action = await vscode.window.showWarningMessage(
      "Research Analyser server is not running. Start it?",
      "Start Server",
      "Cancel"
    );
    if (action !== "Start Server") { return; }

    await vscode.commands.executeCommand("researchAnalyser.startServer");
    // Wait for server to come up
    await new Promise((r) => setTimeout(r, 5000));
    const retryAlive = await client.health();
    if (!retryAlive) {
      vscode.window.showErrorMessage("Server did not start. Please start it manually.");
      return;
    }
  }

  // Pick diagram engine
  const cfg = vscode.workspace.getConfiguration("researchAnalyser");
  const diagramEngine = cfg.get<string>("diagramEngine", "paperbanana");

  vscode.commands.executeCommand("setContext", "researchAnalyser.serverRunning", true);

  const req = { source: src, options: { diagram_engine: diagramEngine } };
  const cancelSource = new AbortController();

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Research Analyser",
      cancellable: true,
    },
    async (progress, token) => {
      token.onCancellationRequested(() => cancelSource.abort());
      progress.report({ message: "Starting analysis…", increment: 0 });

      try {
        const report = await client.analyseStream(
          req,
          (evt) => {
            progress.report({ message: evt.message, increment: evt.pct });
          },
          cancelSource.signal
        );

        store.load(report, src!);
        const eq = report.extracted_content.equations.length;
        const score = report.review ? ` · score ${report.review.overall_score.toFixed(2)}` : "";
        vscode.window.showInformationMessage(
          `Analysis complete — ${eq} equations${score}`
        );
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          vscode.window.showInformationMessage("Analysis cancelled.");
        } else {
          vscode.window.showErrorMessage(`Analysis failed: ${(e as Error).message}`);
        }
      }
    }
  );
}
