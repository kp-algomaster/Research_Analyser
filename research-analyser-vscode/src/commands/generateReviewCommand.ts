import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { ResearchAnalyserClient } from "../api/ResearchAnalyserClient";

/**
 * Run agentic peer review on the currently loaded report or a new source.
 */
export async function generateReviewCommand(
  store: ReportStore,
  client: ResearchAnalyserClient
): Promise<void> {
  // Determine source — from loaded report or user input
  let src: string | undefined;
  const state = store.state;
  if (state.status === "loaded") {
    const reuse = await vscode.window.showQuickPick(
      [
        { label: "Use loaded paper", description: state.source, value: "loaded" },
        { label: "Enter new URL / arXiv ID", value: "new" },
      ],
      { placeHolder: "Which paper to review?" }
    );
    if (!reuse) { return; }
    src = reuse.value === "loaded" ? state.source : undefined;
  }

  if (!src) {
    src = await vscode.window.showInputBox({
      prompt: "Enter PDF path, URL, arXiv ID, or DOI",
      placeHolder: "e.g. 2511.19740 or https://arxiv.org/abs/2511.19740",
      ignoreFocusOut: true,
    });
  }
  if (!src) { return; }

  // Health check
  const alive = await client.health();
  if (!alive) {
    const action = await vscode.window.showWarningMessage(
      "Backend server is not running.",
      "Start Server",
      "Cancel"
    );
    if (action === "Start Server") {
      await vscode.commands.executeCommand("researchAnalyser.startServer");
      await new Promise((r) => setTimeout(r, 6000));
      const retryAlive = await client.health();
      if (!retryAlive) {
        vscode.window.showErrorMessage("Server still not ready. Please try again.");
        return;
      }
    } else {
      return;
    }
  }

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Research Analyser",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: "Generating peer review…" });

      try {
        const report = await client.analyse({
          source: src!,
          options: {
            generate_review: true,
            generate_diagrams: false,
            generate_audio: false,
          },
        });

        store.load(report, src!);

        const score = report.review
          ? `Score: ${report.review.overall_score.toFixed(2)}`
          : "Review complete";
        vscode.window.showInformationMessage(`Peer review generated — ${score}`);
      } catch (e) {
        vscode.window.showErrorMessage(`Review failed: ${(e as Error).message}`);
      }
    }
  );
}
