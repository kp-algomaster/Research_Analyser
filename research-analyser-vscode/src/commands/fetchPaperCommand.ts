import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { ResearchAnalyserClient, FetchResult } from "../api/ResearchAnalyserClient";

/**
 * Fetch a paper from arXiv URL / ID / DOI / URL.
 * Downloads PDF + metadata and offers to proceed to full analysis.
 */
export async function fetchPaperCommand(
  store: ReportStore,
  client: ResearchAnalyserClient,
  prefillSource?: string
): Promise<void> {
  let src = prefillSource;
  if (!src) {
    src = await vscode.window.showInputBox({
      prompt: "Enter arXiv URL, arXiv ID, DOI, or PDF URL",
      placeHolder: "e.g. https://arxiv.org/abs/2511.19740 or 2511.19740",
      ignoreFocusOut: true,
    });
    if (!src) { return; }
  }

  // Health check
  const alive = await client.health();
  if (!alive) {
    vscode.window.showErrorMessage(
      "Research Analyser server is not running. Start it first (⇧⌘R → Start Server)."
    );
    return;
  }

  let result: FetchResult;
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Research Analyser",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: "Fetching paper…" });

      try {
        result = await client.fetchPaper(src!);
      } catch (e) {
        vscode.window.showErrorMessage(`Fetch failed: ${(e as Error).message}`);
        return;
      }

      // Display metadata
      const sizeMB = (result.pdf_size_bytes / (1024 * 1024)).toFixed(1);
      const meta = result.metadata;
      const title = meta?.title ?? "Unknown title";
      const authors = meta?.authors?.join(", ") ?? "Unknown authors";

      const detail = [
        `**${title}**`,
        `Authors: ${authors}`,
        meta?.abstract ? `Abstract: ${meta.abstract.substring(0, 200)}…` : "",
        `PDF: ${sizeMB} MB · Type: ${result.source_type}`,
      ]
        .filter(Boolean)
        .join("\n");

      const action = await vscode.window.showInformationMessage(
        `Fetched: ${title} (${sizeMB} MB)`,
        { modal: false, detail },
        "Analyse Now",
        "Open PDF Location"
      );

      if (action === "Analyse Now") {
        vscode.commands.executeCommand("researchAnalyser.analyse", src);
      } else if (action === "Open PDF Location") {
        const uri = vscode.Uri.file(result.pdf_path);
        vscode.commands.executeCommand("revealFileInOS", uri);
      }
    }
  );
}
