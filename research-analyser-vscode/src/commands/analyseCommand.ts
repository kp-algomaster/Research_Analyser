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

  // Health check — auto-start if not running (no prompt)
  const alive = await client.health();
  if (!alive) {
    vscode.window.showInformationMessage("Research Analyser: Starting server…");
    await vscode.commands.executeCommand("researchAnalyser.startServer");
    // Give server up to 15 s to respond (pip check + uvicorn boot)
    let ready = false;
    for (let i = 0; i < 15; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      if (await client.health()) { ready = true; break; }
    }
    if (!ready) {
      vscode.window.showErrorMessage(
        "Research Analyser server did not start in time. Check the terminal for errors."
      );
      return;
    }
  }

  // Pick diagram engine
  const cfg = vscode.workspace.getConfiguration("researchAnalyser");
  const diagramEngine = cfg.get<string>("diagramEngine", "paperbanana");

  vscode.commands.executeCommand("setContext", "researchAnalyser.serverRunning", true);

  const req = { source: src, options: { diagram_engine: diagramEngine } };

  // ProgressLocation.Window keeps the spinner in the status bar so it never
  // overlaps other panels (e.g. the Claude chat input box).
  // A completion/error notification is shown separately when done.
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Window,
      title: "Research Analyser",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: "Starting analysis…" });

      try {
        const report = await client.analyseStream(
          req,
          (evt) => {
            // message only — Window location has no progress bar
            progress.report({ message: evt.message });
          },
        );

        store.load(report, src!);
        const eq = report.extracted_content.equations.length;
        const score = report.review ? ` · score ${report.review.overall_score.toFixed(2)}` : "";
        vscode.window.showInformationMessage(
          `Research Analyser: complete — ${eq} equations${score}`
        );
      } catch (e) {
        const msg = (e as Error).message ?? "";
        const sslKeywords = ["SSL", "ssl", "certificate", "CERTIFICATE_VERIFY_FAILED"];
        if (sslKeywords.some((kw) => msg.includes(kw))) {
          const action = await vscode.window.showErrorMessage(
            `Research Analyser: SSL error fetching paper. You may need to disable SSL verification or add a custom CA certificate.`,
            "Open SSL Settings"
          );
          if (action === "Open SSL Settings") {
            vscode.commands.executeCommand(
              "workbench.action.openSettings",
              "researchAnalyser.network"
            );
          }
        } else {
          vscode.window.showErrorMessage(`Research Analyser: analysis failed — ${msg}`);
        }
      }
    }
  );
}
