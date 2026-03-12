import * as vscode from "vscode";
import { AnalysisReport, AnalyseRequest, ProgressEvent } from "../types";

// ---------------------------------------------------------------------------
// Types for new endpoints
// ---------------------------------------------------------------------------

export interface FetchResult {
  source_type: string;
  pdf_path: string;
  pdf_size_bytes: number;
  metadata: {
    arxiv_id?: string;
    title?: string;
    authors?: string[];
    abstract?: string;
  } | null;
}

export interface MonkeyOCRStatus {
  installed: boolean;
  model_name: string;
  model_path: string | null;
  size_mb: number | null;
  file_count: number | null;
  complete: boolean | null;
  expected_size_gb: number | null;
  cache_dir: string | null;
  variant: string;    // "standard" | "apple_silicon" | "none"
  device_type: string; // "apple_silicon" | "cuda" | "cpu"
  message: string;
}

export interface MonkeyOCRDownloadResult {
  success: boolean;
  model_name: string;
  model_path: string | null;
  size_mb: number | null;
  file_count: number | null;
  variant: string;
  message: string;
}

export interface MonkeyOCRDeleteResult {
  success: boolean;
  deleted_path: string | null;
  freed_mb: number | null;
  message: string;
}

export interface DiagramResult {
  diagram_type: string;
  image_path: string | null;
  svg_path: string | null;
  png_path: string | null;
  mermaid_code: string | null;
  is_fallback: boolean;
  message: string | null;
}

export interface DeviceInfo {
  device_type: string;   // "apple_silicon" | "cuda" | "cpu"
  device_name: string;   // e.g. "Apple M4 Pro", "NVIDIA RTX 4090"
  mps_available: boolean;
  cuda_available: boolean;
  recommended_variant: string; // "apple_silicon" | "standard"
}

// ---------------------------------------------------------------------------
// Client interface
// ---------------------------------------------------------------------------

export interface IResearchAnalyserClient {
  health(): Promise<boolean>;
  getLatestReport(): Promise<AnalysisReport | null>;
  analyse(req: AnalyseRequest): Promise<AnalysisReport>;
  analyseStream(
    req: AnalyseRequest,
    onProgress: (event: ProgressEvent) => void,
    signal?: AbortSignal
  ): Promise<AnalysisReport>;
  fetchPaper(source: string): Promise<FetchResult>;
  deviceInfo(): Promise<DeviceInfo>;
  monkeyOcrStatus(): Promise<MonkeyOCRStatus>;
  downloadMonkeyOcr(): Promise<MonkeyOCRDownloadResult>;
  deleteMonkeyOcr(): Promise<MonkeyOCRDeleteResult>;
  generateDiagram(text: string, diagramType: string): Promise<DiagramResult>;
  generateDiagramStream(
    text: string,
    diagramType: string,
    engine: string,
    onProgress: (event: import("../types").ProgressEvent) => void,
    signal?: AbortSignal
  ): Promise<DiagramResult>;
}

function getBaseUrl(): string {
  return vscode.workspace
    .getConfiguration("researchAnalyser")
    .get<string>("apiUrl", "http://localhost:8000");
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...init, signal: controller.signal });
    clearTimeout(id);
    return resp;
  } catch (e) {
    clearTimeout(id);
    throw e;
  }
}

export class ResearchAnalyserClient implements IResearchAnalyserClient {
  async health(): Promise<boolean> {
    try {
      const resp = await fetchWithTimeout(
        `${getBaseUrl()}/health`,
        { method: "GET" },
        2000
      );
      if (!resp.ok) { return false; }
      // Verify this is the Research Analyser server, not another service on the same port.
      const body = await resp.json().catch(() => null) as { status?: string } | null;
      return body?.status === "ok";
    } catch {
      return false;
    }
  }

  async getLatestReport(): Promise<AnalysisReport | null> {
    try {
      const resp = await fetchWithTimeout(
        `${getBaseUrl()}/report/latest`,
        { method: "GET" },
        5000
      );
      if (resp.status === 404) { return null; }
      if (!resp.ok) {
        vscode.window.showErrorMessage(`Server error ${resp.status} fetching latest report`);
        return null;
      }
      return (await resp.json()) as AnalysisReport;
    } catch {
      return null;
    }
  }

  async analyse(req: AnalyseRequest): Promise<AnalysisReport> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/analyse`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      },
      300_000
    );
    if (resp.status === 422) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(`Invalid input: ${JSON.stringify(body)}`);
    }
    if (!resp.ok) {
      throw new Error(`Server error ${resp.status}`);
    }
    return (await resp.json()) as AnalysisReport;
  }

  async analyseStream(
    req: AnalyseRequest,
    onProgress: (event: ProgressEvent) => void,
    signal?: AbortSignal
  ): Promise<AnalysisReport> {
    const resp = await fetch(`${getBaseUrl()}/analyse/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });

    if (!resp.ok) {
      throw new Error(`Server error ${resp.status}`);
    }
    if (!resp.body) {
      throw new Error("Server returned no body for SSE stream");
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "";

    return new Promise<AnalysisReport>((resolve, reject) => {
      const pump = async (): Promise<void> => {
        try {
          // eslint-disable-next-line no-constant-condition
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              reject(new Error("SSE stream ended without completion event"));
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              if (line.startsWith("event:")) {
                currentEvent = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                const dataStr = line.slice(5).trim();
                try {
                  const data = JSON.parse(dataStr);
                  if (currentEvent === "progress") {
                    onProgress(data as ProgressEvent);
                  } else if (currentEvent === "complete") {
                    resolve(data as AnalysisReport);
                    return;
                  } else if (currentEvent === "error") {
                    reject(new Error(data.message ?? "Analysis failed"));
                    return;
                  }
                } catch {
                  // malformed JSON line — skip
                }
                currentEvent = "";
              }
            }
          }
        } catch (e) {
          reject(e);
        }
      };
      pump();
    });
  }

  // -----------------------------------------------------------------------
  // Paper fetching (download PDF + metadata, no analysis)
  // -----------------------------------------------------------------------

  async fetchPaper(source: string): Promise<FetchResult> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/fetch`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      },
      120_000
    );
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`Fetch failed (${resp.status}): ${body}`);
    }
    return (await resp.json()) as FetchResult;
  }

  // -----------------------------------------------------------------------
  // Device info
  // -----------------------------------------------------------------------

  async deviceInfo(): Promise<DeviceInfo> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/device/info`,
      { method: "GET" },
      5_000
    );
    if (!resp.ok) {
      throw new Error(`Device info failed (${resp.status})`);
    }
    return (await resp.json()) as DeviceInfo;
  }

  // -----------------------------------------------------------------------
  // MonkeyOCR model management
  // -----------------------------------------------------------------------

  async monkeyOcrStatus(): Promise<MonkeyOCRStatus> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/monkeyocr/status`,
      { method: "GET" },
      10_000
    );
    if (!resp.ok) {
      throw new Error(`Status check failed (${resp.status})`);
    }
    return (await resp.json()) as MonkeyOCRStatus;
  }

  async downloadMonkeyOcr(): Promise<MonkeyOCRDownloadResult> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/monkeyocr/download`,
      { method: "POST" },
      600_000 // up to 10 min for large model
    );
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`Download failed (${resp.status}): ${body}`);
    }
    return (await resp.json()) as MonkeyOCRDownloadResult;
  }

  async deleteMonkeyOcr(): Promise<MonkeyOCRDeleteResult> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/monkeyocr/delete`,
      { method: "DELETE" },
      30_000
    );
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`Delete failed (${resp.status}): ${body}`);
    }
    return (await resp.json()) as MonkeyOCRDeleteResult;
  }

  // -----------------------------------------------------------------------
  // Diagram generation from text
  // -----------------------------------------------------------------------

  async generateDiagramStream(
    text: string,
    diagramType: string,
    engine: string,
    onProgress: (event: import("../types").ProgressEvent) => void,
    signal?: AbortSignal
  ): Promise<DiagramResult> {
    const resp = await fetch(`${getBaseUrl()}/diagrams/generate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, diagram_type: diagramType, engine }),
      signal,
    });

    if (!resp.ok) {
      throw new Error(`Server error ${resp.status}`);
    }
    if (!resp.body) {
      throw new Error("Server returned no body for SSE stream");
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "";

    return new Promise<DiagramResult>((resolve, reject) => {
      const pump = async (): Promise<void> => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              reject(new Error("SSE stream ended without completion event"));
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              if (line.startsWith("event:")) {
                currentEvent = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                const dataStr = line.slice(5).trim();
                try {
                  const data = JSON.parse(dataStr);
                  if (currentEvent === "progress") {
                    onProgress(data as import("../types").ProgressEvent);
                  } else if (currentEvent === "complete") {
                    resolve(data as DiagramResult);
                    return;
                  } else if (currentEvent === "error") {
                    reject(new Error(data.message ?? "Diagram generation failed"));
                    return;
                  }
                } catch {
                  // malformed JSON — skip
                }
                currentEvent = "";
              }
            }
          }
        } catch (e) {
          reject(e);
        }
      };
      pump();
    });
  }

  async generateDiagram(text: string, diagramType: string, engine: string = "paperbanana"): Promise<DiagramResult> {
    const resp = await fetchWithTimeout(
      `${getBaseUrl()}/diagrams/generate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, diagram_type: diagramType, engine }),
      },
      300_000 // up to 5 min for pipeline
    );
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`Diagram generation failed (${resp.status}): ${body}`);
    }
    return (await resp.json()) as DiagramResult;
  }
}
