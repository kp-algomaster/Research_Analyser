import * as vscode from "vscode";
import { ResearchAnalyserClient } from "../api/ResearchAnalyserClient";

/**
 * Generate methodology / architecture / results diagrams from pasted text.
 *
 * Uses the PaperBanana pipeline on the backend (/diagrams/generate).
 */
export async function textToDiagramsCommand(client: ResearchAnalyserClient): Promise<void> {
  // Pick diagram engine
  const engine = await vscode.window.showQuickPick(
    [
      {
        label: "Beautiful Mermaid",
        value: "beautiful_mermaid",
        description: "Local rendering, no API key needed",
      },
      {
        label: "PaperBanana",
        value: "paperbanana",
        description: "AI-powered (requires Google API key)",
      },
    ],
    { placeHolder: "Choose diagram engine", title: "Text → Diagrams" }
  );
  if (!engine) { return; }

  // Pick diagram type
  const diagramType = await vscode.window.showQuickPick(
    [
      { label: "Methodology", value: "methodology", description: "Step-by-step method flow" },
      { label: "Architecture", value: "architecture", description: "System / model architecture" },
      { label: "Results", value: "results", description: "Results comparison plot" },
    ],
    { placeHolder: "Choose diagram type", title: "Text → Diagrams" }
  );
  if (!diagramType) { return; }

  // Get text input — from selection or manual entry
  const editor = vscode.window.activeTextEditor;
  let text = editor?.document.getText(editor.selection);
  if (!text || text.trim().length === 0) {
    text = await vscode.window.showInputBox({
      prompt: "Paste or type the text to convert into a diagram",
      placeHolder: "We propose a transformer-based architecture with …",
      ignoreFocusOut: true,
    });
  }
  if (!text || text.trim().length === 0) { return; }

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
      // Wait a moment, then retry
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

  // Call the API with SSE progress streaming
  const cancelSource = new AbortController();
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Generating diagram…",
      cancellable: true,
    },
    async (progress, token) => {
      token.onCancellationRequested(() => cancelSource.abort());
      progress.report({ message: `Creating ${(diagramType as { label: string; value: string }).label} diagram…`, increment: 0 });

      try {
        const result = await client.generateDiagramStream(
          text!,
          (diagramType as { label: string; value: string }).value,
          (engine as { label: string; value: string }).value,
          (evt) => {
            progress.report({ message: evt.message, increment: evt.pct });
          },
          cancelSource.signal
        );

        if (result.image_path || result.svg_path || result.png_path) {
          // Resolve paths
          const resolve = (p: string | null | undefined): string | null => {
            if (!p) { return null; }
            if (p.startsWith("/")) { return p; }
            const wf = vscode.workspace.workspaceFolders;
            if (wf?.length) { return vscode.Uri.joinPath(wf[0].uri, p).fsPath; }
            return p;
          };

          const svgPath = resolve(result.svg_path);
          const pngPath = resolve(result.png_path);
          const mainPath = resolve(result.image_path) ?? pngPath ?? svgPath;

          const actions: string[] = [];
          if (pngPath) { actions.push("Open PNG"); }
          if (svgPath) { actions.push("Open SVG"); }
          actions.push("Reveal in Finder");

          const summaryParts = [`Diagram: ${result.diagram_type}`];
          if (pngPath) { summaryParts.push(`PNG: ${pngPath}`); }
          if (svgPath) { summaryParts.push(`SVG: ${svgPath}`); }

          const action = await vscode.window.showInformationMessage(
            summaryParts.join("\n"),
            ...actions
          );
          if (action === "Open PNG" && pngPath) {
            await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(pngPath));
          } else if (action === "Open SVG" && svgPath) {
            await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(svgPath));
          } else if (action === "Reveal in Finder" && mainPath) {
            await vscode.commands.executeCommand("revealFileInOS", vscode.Uri.file(mainPath));
          }
        } else {
          vscode.window.showWarningMessage(
            `Diagram generated but no image path returned. ${result.message ?? ""}`
          );
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          vscode.window.showInformationMessage("Diagram generation cancelled.");
        } else {
          vscode.window.showErrorMessage(`Diagram generation failed: ${(e as Error).message}`);
        }
      }
    }
  );
}
