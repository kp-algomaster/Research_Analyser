import * as vscode from "vscode";
import { ResearchAnalyserClient, MonkeyOCRStatus, DeviceInfo } from "../api/ResearchAnalyserClient";
import { ResearchTreeDataProvider } from "../providers/ResearchTreeDataProvider";

/**
 * Device-type label for UI display.
 */
function deviceLabel(device: DeviceInfo): string {
  if (device.device_type === "apple_silicon") {
    return `Apple Silicon (${device.device_name})`;
  }
  if (device.device_type === "cuda") {
    return `NVIDIA GPU (${device.device_name})`;
  }
  return "CPU";
}

/**
 * Variant label for UI display.
 */
function variantLabel(variant: string): string {
  if (variant === "apple_silicon") { return "Apple Silicon (MLX)"; }
  if (variant === "standard") { return "Standard (HuggingFace)"; }
  return "Not installed";
}

/**
 * Format a human-readable size string.
 */
function formatSize(mb: number | null): string {
  if (mb == null) { return "unknown size"; }
  if (mb >= 1024) { return `${(mb / 1024).toFixed(1)} GB`; }
  return `${mb.toFixed(0)} MB`;
}

/**
 * Build a multi-line status summary for MonkeyOCR.
 */
function buildStatusLines(status: MonkeyOCRStatus): string[] {
  const lines: string[] = [];
  lines.push(`Model: ${status.model_name}`);
  lines.push(`Variant: ${variantLabel(status.variant)}`);
  lines.push(`Device: ${status.device_type === "apple_silicon" ? "Apple Silicon" : status.device_type === "cuda" ? "NVIDIA CUDA" : "CPU"}`);
  lines.push(`Status: ${status.installed ? "Installed" : "Not installed"}`);
  if (status.installed) {
    const sizeActual = formatSize(status.size_mb);
    if (status.variant === "apple_silicon") {
      lines.push(`Size: ${sizeActual}`);
    } else {
      const sizeExpected = status.expected_size_gb
        ? `${status.expected_size_gb} GB`
        : "unknown";
      lines.push(`Size: ${sizeActual} (expected ~${sizeExpected})`);
    }
    lines.push(
      `Integrity: ${status.complete ? "Complete ✓" : "Incomplete / Needs setup ⚠"}`
    );
    if (status.file_count != null) {
      lines.push(`Files: ${status.file_count}`);
    }
  }
  if (status.model_path) {
    lines.push(`Path: ${status.model_path}`);
  }
  if (status.cache_dir) {
    lines.push(`Cache dir: ${status.cache_dir}`);
  }
  return lines;
}

/** Ensure HF_TOKEN is configured; returns true if we should proceed. */
async function ensureHfToken(): Promise<boolean> {
  const hfToken = vscode.workspace
    .getConfiguration("researchAnalyser.keys")
    .get<string>("huggingface", "");

  if (hfToken) { return true; }

  const choice = await vscode.window.showWarningMessage(
    "HuggingFace Token (HF_TOKEN) is not set. MonkeyOCR may require it for gated model access.",
    "Open Settings",
    "Continue Anyway"
  );
  if (choice === "Open Settings") {
    vscode.commands.executeCommand(
      "workbench.action.openSettings",
      "researchAnalyser.keys.huggingface"
    );
    return false;
  }
  return choice === "Continue Anyway";
}

/** Run the download and update sidebar tree status. */
async function runDownload(
  client: ResearchAnalyserClient,
  treeProvider: ResearchTreeDataProvider,
  modelName: string,
  deviceType: string
): Promise<void> {
  const variantMsg = deviceType === "apple_silicon"
    ? "Setting up Apple Silicon (MLX) MonkeyOCR…"
    : `Downloading ${modelName}…`;
  treeProvider.setDownloadStatus(
    "downloading",
    `${variantMsg} This may take several minutes.`
  );

  try {
    const result = await client.downloadMonkeyOcr();

    if (result.success) {
      const details: string[] = [
        `MonkeyOCR (${variantLabel(result.variant)}) ready!`,
        `Size: ${formatSize(result.size_mb)}`,
      ];
      if (result.file_count != null) { details.push(`Files: ${result.file_count}`); }
      if (result.model_path) { details.push(`Path: ${result.model_path}`); }

      treeProvider.setDownloadStatus("complete", `${modelName} ready ✓`);

      const action = await vscode.window.showInformationMessage(
        details.join("\n"),
        "Open Folder",
        "OK"
      );
      if (action === "Open Folder" && result.model_path) {
        vscode.commands.executeCommand(
          "revealFileInOS",
          vscode.Uri.file(result.model_path)
        );
      }
      setTimeout(() => treeProvider.setDownloadStatus("idle"), 8000);
    } else {
      treeProvider.setDownloadStatus("error", `Setup failed: ${result.message}`);
      vscode.window.showErrorMessage(`MonkeyOCR setup failed: ${result.message}`);
      setTimeout(() => treeProvider.setDownloadStatus("idle"), 15000);
    }
  } catch (e) {
    const msg = (e as Error).message;
    treeProvider.setDownloadStatus("error", `Setup failed: ${msg}`);
    vscode.window.showErrorMessage(`MonkeyOCR setup failed: ${msg}`);
    setTimeout(() => treeProvider.setDownloadStatus("idle"), 15000);
  }
}

/** Delete the model and update sidebar tree status. */
async function runDelete(
  client: ResearchAnalyserClient,
  treeProvider: ResearchTreeDataProvider,
  modelName: string
): Promise<void> {
  const confirm = await vscode.window.showWarningMessage(
    `Are you sure you want to delete ${modelName}? This will free disk space but you'll need to re-download for offline OCR.`,
    { modal: true },
    "Delete",
    "Cancel"
  );
  if (confirm !== "Delete") { return; }

  treeProvider.setDownloadStatus("downloading", `Deleting ${modelName}…`);

  try {
    const result = await client.deleteMonkeyOcr();
    if (result.success) {
      treeProvider.setDownloadStatus("complete", `${modelName} deleted (${formatSize(result.freed_mb)} freed)`);
      vscode.window.showInformationMessage(
        `MonkeyOCR deleted. ${formatSize(result.freed_mb)} freed.`
      );
      setTimeout(() => treeProvider.setDownloadStatus("idle"), 8000);
    } else {
      treeProvider.setDownloadStatus("error", `Delete failed: ${result.message}`);
      vscode.window.showErrorMessage(`Delete failed: ${result.message}`);
      setTimeout(() => treeProvider.setDownloadStatus("idle"), 15000);
    }
  } catch (e) {
    const msg = (e as Error).message;
    treeProvider.setDownloadStatus("error", `Delete failed: ${msg}`);
    vscode.window.showErrorMessage(`Delete failed: ${msg}`);
    setTimeout(() => treeProvider.setDownloadStatus("idle"), 15000);
  }
}

/**
 * MonkeyOCR model manager — check status, download, re-download, or delete.
 */
export async function downloadMonkeyOcrCommand(
  client: ResearchAnalyserClient,
  treeProvider: ResearchTreeDataProvider
): Promise<void> {
  // Health check
  const alive = await client.health();
  if (!alive) {
    vscode.window.showErrorMessage(
      "Research Analyser server is not running. Start it first."
    );
    return;
  }

  // Check current status
  let status: MonkeyOCRStatus;
  try {
    status = await client.monkeyOcrStatus();
  } catch (e) {
    vscode.window.showErrorMessage(
      `Failed to check MonkeyOCR status: ${(e as Error).message}`
    );
    return;
  }

  const statusLines = buildStatusLines(status);

  // ── Model is installed ──────────────────────────────────────────────
  if (status.installed) {
    const integrityLabel = status.complete
      ? "✓ Setup verified complete"
      : "⚠ Setup appears incomplete — consider re-installing";

    const actions: string[] = [];
    if (status.model_path) { actions.push("Open Folder"); }
    actions.push("Re-download");
    actions.push("Delete");

    const action = await vscode.window.showInformationMessage(
      statusLines.join("\n") + `\n\n${integrityLabel}`,
      { modal: true },
      ...actions
    );

    if (action === "Open Folder" && status.model_path) {
      vscode.commands.executeCommand(
        "revealFileInOS",
        vscode.Uri.file(status.model_path)
      );
      return;
    }

    if (action === "Re-download") {
      if (status.device_type !== "apple_silicon") {
        if (!(await ensureHfToken())) { return; }
      }
      await runDownload(client, treeProvider, status.model_name, status.device_type);
      return;
    }

    if (action === "Delete") {
      await runDelete(client, treeProvider, status.model_name);
      return;
    }

    return; // cancelled
  }

  // ── Model is NOT installed ──────────────────────────────────────────
  const isAppleSilicon = status.device_type === "apple_silicon";
  const variantDesc = isAppleSilicon
    ? "Apple Silicon (MLX) — 3× faster on M-series chips"
    : `Standard (${status.model_name})`;
  const sizeNote = isAppleSilicon
    ? "The setup will clone the repo and install dependencies (~5-10 min)."
    : (status.expected_size_gb ? `Expected size: ~${status.expected_size_gb} GB` : "");

  const action = await vscode.window.showInformationMessage(
    `MonkeyOCR is not installed.\n\n` +
      `Detected: ${status.device_type === "apple_silicon" ? "Apple Silicon" : status.device_type === "cuda" ? "NVIDIA GPU" : "CPU"}\n` +
      `Recommended variant: ${variantDesc}\n` +
      (sizeNote ? `${sizeNote}\n` : "") +
      (status.cache_dir ? `Cache dir: ${status.cache_dir}\n` : "") +
      (isAppleSilicon ? "" : "(requires HF_TOKEN)"),
    { modal: true },
    isAppleSilicon ? "Setup Apple Silicon OCR" : "Download Now",
    "Cancel"
  );
  if (!action || action === "Cancel") { return; }

  if (!isAppleSilicon) {
    if (!(await ensureHfToken())) { return; }
  }
  await runDownload(client, treeProvider, status.model_name, status.device_type);
}
