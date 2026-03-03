// Webview-side script — runs inside the webview sandbox (no Node.js APIs)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const katex: any;
declare function acquireVsCodeApi(): {
  postMessage(msg: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
};

const vscode = acquireVsCodeApi();

// State — persisted via vscode.setState for webview restore
function saveReport(report: unknown): void {
  vscode.setState({ report });
}
function clearSavedReport(): void {
  vscode.setState({ report: null });
}

// Tab switching
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const id = (tab as HTMLElement).dataset["tab"];
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`panel-${id}`)?.classList.add("active");
  });
});

// Message handling
window.addEventListener("message", (event) => {
  const msg = event.data as {
    type: string;
    report?: unknown;
    id?: string;
    kind?: string;
  };

  switch (msg.type) {
    case "loadReport":
      saveReport(msg.report);
      renderAll(msg.report as Report);
      break;
    case "clearReport":
      clearSavedReport();
      renderEmpty();
      break;
    case "scrollToEquation":
      scrollToEquation(msg.id ?? "");
      break;
    case "setTheme":
      // KaTeX adapts to CSS variables automatically
      break;
  }
});

// Notify extension we're ready
vscode.postMessage({ type: "ready" });

// Restore previous state if available
const previousState = vscode.getState() as { report?: Report } | undefined;
if (previousState?.report) {
  renderAll(previousState.report);
}

// Type stubs (mirrors src/types/index.ts)
interface Equation { id: string; label: string | null; latex: string; section: string; is_inline: boolean; description: string | null; }
interface Section { title: string; content: string; level: number; section_number: string; }
interface PeerReview { overall_score: number; confidence: number; strengths: string[]; weaknesses: string[]; dimensions: Record<string, { name: string; score: number; comments: string }>; decision: string; }
interface GeneratedDiagram { diagram_type: string; image_path: string; caption: string; is_fallback: boolean; error: string | null; format: string; }
interface PaperSummary { one_sentence: string; abstract_summary: string; methodology_summary: string; results_summary: string; conclusions: string; }
interface Report {
  extracted_content: { title: string; authors: string[]; abstract: string; sections: Section[]; equations: Equation[] };
  summary: PaperSummary | null;
  review: PeerReview | null;
  diagrams: GeneratedDiagram[];
  key_points: { point: string; evidence: string; section: string; importance: string }[];
  metadata: { created_at: string; ocr_model: string; processing_time_seconds: number };
  storm_report: string | null;
}

function renderKatex(latex: string, display = false): string {
  try {
    return katex.renderToString(latex, { throwOnError: false, displayMode: display, output: "html" });
  } catch {
    return `<code>${latex}</code>`;
  }
}

function renderAll(report: Report): void {
  renderSummary(report);
  renderEquations(report.extracted_content.equations);
  renderDiagrams(report.diagrams);
  renderReview(report.review);
  renderSpec(report.extracted_content.sections);
}

function renderEmpty(): void {
  ["summary", "equations", "diagrams", "review", "spec"].forEach((id) => {
    const el = document.getElementById(`panel-${id}`);
    if (el) { el.innerHTML = '<div class="empty-state">No report loaded</div>'; }
  });
}

function renderSummary(report: Report): void {
  const el = document.getElementById("panel-summary");
  if (!el) { return; }
  const s = report.summary;
  const m = report.metadata;
  el.innerHTML = `
    <div class="card">
      <h2>${esc(report.extracted_content.title)}</h2>
      <p><em>${esc(report.extracted_content.authors.join(", "))}</em></p>
      <p>${esc(report.extracted_content.abstract)}</p>
    </div>
    ${s ? `
    <div class="card">
      <h3>Summary</h3>
      <p>${esc(s.one_sentence)}</p>
      <h4>Methodology</h4><p>${esc(s.methodology_summary)}</p>
      <h4>Results</h4><p>${esc(s.results_summary)}</p>
      <h4>Conclusions</h4><p>${esc(s.conclusions)}</p>
    </div>` : ""}
    <div class="card">
      <small>OCR: ${esc(m.ocr_model)} · processed in ${m.processing_time_seconds.toFixed(1)}s · ${esc(m.created_at.slice(0, 10))}</small>
    </div>`;
}

function renderEquations(equations: Equation[]): void {
  const el = document.getElementById("panel-equations");
  if (!el) { return; }
  if (equations.length === 0) { el.innerHTML = '<div class="empty-state">No equations</div>'; return; }
  el.innerHTML = equations.map((eq) => `
    <div class="eq-card" id="eq-${esc(eq.id)}">
      <strong>${esc(eq.label ?? eq.id)}</strong> <em>§${esc(eq.section)}</em>
      <div>${renderKatex(eq.latex, true)}</div>
      ${eq.description ? `<p>${esc(eq.description)}</p>` : ""}
      <div class="eq-actions">
        <button onclick="insertEquation(${JSON.stringify(eq.latex)}, ${JSON.stringify(eq.label)}, 'comment')">Insert as comment</button>
        <button onclick="copyEquation(${JSON.stringify(eq.latex)})">Copy LaTeX</button>
      </div>
    </div>`).join("");
}

function renderDiagrams(diagrams: GeneratedDiagram[]): void {
  const el = document.getElementById("panel-diagrams");
  if (!el) { return; }
  if (!diagrams || diagrams.length === 0) { el.innerHTML = '<div class="empty-state">No diagrams generated</div>'; return; }
  el.innerHTML = diagrams.map((d) => `
    <div class="card">
      <strong>${esc(d.diagram_type)}</strong>${d.is_fallback ? " (fallback)" : ""}
      ${d.error ? `<p style="color:var(--vscode-errorForeground)">${esc(d.error)}</p>` : `<p>${esc(d.caption)}</p>`}
    </div>`).join("");
}

function renderReview(review: PeerReview | null): void {
  const el = document.getElementById("panel-review");
  if (!el) { return; }
  if (!review) { el.innerHTML = '<div class="empty-state">No peer review</div>'; return; }
  const scorePct = Math.min(100, Math.max(0, review.overall_score * 25));
  el.innerHTML = `
    <div class="card">
      <h3>Score: ${review.overall_score.toFixed(2)} / 4</h3>
      <div style="background:var(--vscode-panel-border);border-radius:4px;height:8px">
        <div class="score-bar" style="width:${scorePct}%"></div>
      </div>
      <p>Decision: <strong>${esc(review.decision)}</strong> · Confidence: ${review.confidence}</p>
    </div>
    <div class="card">
      <h4>Strengths</h4>
      <ul>${review.strengths.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
      <h4>Weaknesses</h4>
      <ul>${review.weaknesses.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
    </div>`;
}

function renderSpec(sections: Section[]): void {
  const el = document.getElementById("panel-spec");
  if (!el) { return; }
  el.innerHTML = sections.map((s) => `
    <div class="card">
      <h${Math.min(4, s.level + 2)}>§${esc(s.section_number)} ${esc(s.title)}</h${Math.min(4, s.level + 2)}>
      <p>${esc(s.content).replace(/\$\$(.+?)\$\$/gs, (_: string, l: string) => renderKatex(l, true)).replace(/\$(.+?)\$/g, (_: string, l: string) => renderKatex(l))}</p>
    </div>`).join("");
}

function scrollToEquation(id: string): void {
  // Switch to equations tab
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  document.querySelector('[data-tab="equations"]')?.classList.add("active");
  document.getElementById("panel-equations")?.classList.add("active");
  document.getElementById(`eq-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

// Global button handlers (called from inline onclick)
(window as unknown as Record<string, unknown>)["insertEquation"] = (latex: string, label: string | null, format: string) => {
  vscode.postMessage({ type: "insertEquation", latex, label, format });
};
(window as unknown as Record<string, unknown>)["copyEquation"] = (latex: string) => {
  vscode.postMessage({ type: "copyEquation", latex });
};

function esc(str: string | null | undefined): string {
  if (!str) { return ""; }
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
