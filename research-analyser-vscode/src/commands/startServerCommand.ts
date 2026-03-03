import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { ResearchAnalyserClient } from "../api/ResearchAnalyserClient";

/**
 * Start the Research Analyser FastAPI backend server.
 *
 * Discovers the project's Python venv and uses its uvicorn directly,
 * avoiding PATH issues when VS Code tasks can't find the command.
 */
export async function startServerCommand(client: ResearchAnalyserClient): Promise<void> {
  // Quick health check — maybe it's already running
  const alive = await client.health();
  if (alive) {
    vscode.window.showInformationMessage("Research Analyser server is already running.");
    return;
  }

  // Resolve the project root (workspace folder or parent of extension)
  const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const projectRoot = wsFolder ?? "";

  // Try to find Python / uvicorn inside the venv
  const venvCandidates = [
    path.join(projectRoot, ".venv312", "bin", "uvicorn"),
    path.join(projectRoot, ".venv", "bin", "uvicorn"),
    path.join(projectRoot, "venv", "bin", "uvicorn"),
  ];

  let uvicornPath = "uvicorn"; // fallback
  for (const candidate of venvCandidates) {
    if (fs.existsSync(candidate)) {
      uvicornPath = candidate;
      break;
    }
  }

  // Also try python -m uvicorn as last resort
  const pythonCandidates = [
    path.join(projectRoot, ".venv312", "bin", "python"),
    path.join(projectRoot, ".venv", "bin", "python"),
    path.join(projectRoot, "venv", "bin", "python"),
  ];

  let useModule = false;
  let pythonPath = "python3";
  if (uvicornPath === "uvicorn") {
    // Could not find uvicorn binary directly — use python -m uvicorn
    for (const candidate of pythonCandidates) {
      if (fs.existsSync(candidate)) {
        pythonPath = candidate;
        useModule = true;
        break;
      }
    }
  }

  const cmd = useModule
    ? `${pythonPath} -m uvicorn research_analyser.api:app --host 0.0.0.0 --port 8000`
    : `${uvicornPath} research_analyser.api:app --host 0.0.0.0 --port 8000`;

  const task = new vscode.Task(
    { type: "shell" },
    vscode.TaskScope.Workspace,
    "Research Analyser",
    "research-analyser",
    new vscode.ShellExecution(cmd, { cwd: projectRoot })
  );
  task.isBackground = true;
  task.presentationOptions = {
    reveal: vscode.TaskRevealKind.Always,
    panel: vscode.TaskPanelKind.Dedicated,
  };

  await vscode.tasks.executeTask(task);

  // Wait for server to come up (poll every second, up to 15 s)
  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Starting server…" },
    async (progress) => {
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        progress.report({ message: `Waiting… (${i + 1}s)` });
        const ok = await client.health();
        if (ok) {
          vscode.commands.executeCommand("setContext", "researchAnalyser.serverRunning", true);
          vscode.window.showInformationMessage("Research Analyser server started.");
          return;
        }
      }
      vscode.window.showWarningMessage(
        "Server may still be starting. Check the terminal output."
      );
    }
  );
}
