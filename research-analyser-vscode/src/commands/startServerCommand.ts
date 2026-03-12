import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { ResearchAnalyserClient } from "../api/ResearchAnalyserClient";

/**
 * Persistent venv directory — shared with the macOS launcher.
 * Created once; reused on every subsequent "Start Server" invocation.
 */
const RA_VENV_DIR = path.join(os.homedir(), ".researchanalyser", "venv");

/**
 * Start the Research Analyser FastAPI backend server.
 *
 * First invocation (no venv found):
 *   1. Finds system Python 3 via login-shell PATH (Homebrew, pyenv, etc.)
 *   2. Creates ~/.researchanalyser/venv
 *   3. pip-installs all requirements from the workspace requirements.txt
 *   4. Starts uvicorn — terminal stays open so the user can monitor progress
 *
 * Subsequent invocations (venv already exists):
 *   Runs uvicorn directly from the existing venv — no reinstall.
 */
export async function startServerCommand(client: ResearchAnalyserClient): Promise<void> {
  // Already running?
  const alive = await client.health();
  if (alive) {
    vscode.window.showInformationMessage("Research Analyser server is already running.");
    return;
  }

  const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const projectRoot = wsFolder ?? "";

  // --- Locate an existing venv that already has uvicorn installed ---
  const venvCandidates = [
    RA_VENV_DIR,
    path.join(projectRoot, ".venv312"),
    path.join(projectRoot, ".venv"),
    path.join(projectRoot, "venv"),
  ];

  let uvicornBin: string | undefined;
  for (const v of venvCandidates) {
    const u = path.join(v, "bin", "uvicorn");
    if (fs.existsSync(u)) {
      uvicornBin = u;
      break;
    }
  }

  const isFirstTime = !uvicornBin;
  let shellCmd: string;

  if (!isFirstTime) {
    // --- Subsequent run: start the server directly ---
    shellCmd = `"${uvicornBin}" research_analyser.api:app --host 0.0.0.0 --port 8000`;
  } else {
    // --- First-time setup: create venv → install deps → start server ---
    const venvDir = RA_VENV_DIR;
    const pipBin = path.join(venvDir, "bin", "pip");
    const uvicornNew = path.join(venvDir, "bin", "uvicorn");
    const reqFile = path.join(projectRoot, "requirements.txt");
    const reqArg = fs.existsSync(reqFile) ? reqFile : "";

    const installCmd = reqArg
      ? `"${pipBin}" install -r "${reqArg}"`
      : `"${pipBin}" install fastapi "uvicorn[standard]" sse-starlette python-dotenv pydantic python-multipart httpx aiohttp aiofiles PyMuPDF rich click tqdm Pillow soundfile`;

    // Steps are newline-separated; set -e makes the script fail-fast on any error.
    // The task shell is forced to zsh -l so Homebrew/pyenv/conda are on PATH.
    shellCmd = [
      "set -e",
      `echo "╔══════════════════════════════════════════════════════╗"`,
      `echo "║  Research Analyser — First-time environment setup    ║"`,
      `echo "╚══════════════════════════════════════════════════════╝"`,
      // Discover Python 3.10+; login shell means Homebrew is already in PATH
      `PYTHON=$(command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3.10 2>/dev/null || command -v python3 2>/dev/null)`,
      `[ -z "$PYTHON" ] && echo "ERROR: Python 3.10+ not found. Install via Homebrew: brew install python@3.12" && exit 1`,
      `echo "Using Python: $PYTHON ($($PYTHON --version))"`,
      `echo ""`,
      `echo "--- Creating virtual environment at ${venvDir} ---"`,
      `"$PYTHON" -m venv "${venvDir}"`,
      `"${pipBin}" install --quiet --upgrade pip`,
      `echo ""`,
      `echo "--- Installing packages (this may take 5–15 minutes on first run) ---"`,
      installCmd,
      `echo ""`,
      `echo "=== Setup complete. Starting server… ==="`,
      `echo ""`,
      `"${uvicornNew}" research_analyser.api:app --host 0.0.0.0 --port 8000`,
    ].join("\n");
  }

  const taskLabel = isFirstTime
    ? "Research Analyser — First-time Setup"
    : "Research Analyser";

  // ShellExecution with zsh -l ensures Homebrew / pyenv are on PATH
  const task = new vscode.Task(
    { type: "shell" },
    vscode.TaskScope.Workspace,
    taskLabel,
    "research-analyser",
    new vscode.ShellExecution(shellCmd, {
      cwd: projectRoot,
      executable: "/bin/zsh",
      shellArgs: ["-l", "-c"],
    })
  );
  task.isBackground = true;
  task.presentationOptions = {
    reveal: vscode.TaskRevealKind.Always,
    panel: vscode.TaskPanelKind.Dedicated,
  };

  if (isFirstTime) {
    vscode.window.showInformationMessage(
      "Research Analyser: First-time setup started. " +
        "Watch the terminal — this may take 5–15 minutes while packages are installed."
    );
  }

  await vscode.tasks.executeTask(task);

  // Poll for server readiness.
  // Allow up to 10 minutes on first run (pip installs torch, langgraph, etc.)
  const maxWaitSecs = isFirstTime ? 600 : 30;
  const progressTitle = isFirstTime
    ? "Research Analyser: Installing packages & starting server…"
    : "Research Analyser: Starting server…";

  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: progressTitle },
    async (progress: vscode.Progress<{ message?: string }>) => {
      for (let i = 0; i < maxWaitSecs; i++) {
        await new Promise<void>((r) => setTimeout(r, 1000));
        progress.report({ message: `(${i + 1}s) — check the terminal for progress` });
        const ok = await client.health();
        if (ok) {
          vscode.commands.executeCommand("setContext", "researchAnalyser.serverRunning", true);
          vscode.window.showInformationMessage("Research Analyser server started.");
          return;
        }
      }
      vscode.window.showWarningMessage(
        "Server did not respond in time. Check the terminal output for errors."
      );
    }
  );
}
