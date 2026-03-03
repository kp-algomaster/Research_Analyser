import * as vscode from "vscode";
import { ReportStore } from "../store/ReportStore";
import { AnalysisReport, CoverageItem } from "../types";

type TreeItem = PaperNode | EquationNode | SpecSectionNode | InfoNode | ActionNode | DownloadStatusNode;

export type DownloadState = "idle" | "downloading" | "complete" | "error";

class DownloadStatusNode extends vscode.TreeItem {
  constructor(state: DownloadState, message: string) {
    super(message, vscode.TreeItemCollapsibleState.None);
    switch (state) {
      case "downloading":
        this.iconPath = new vscode.ThemeIcon("sync~spin");
        break;
      case "complete":
        this.iconPath = new vscode.ThemeIcon("pass", new vscode.ThemeColor("charts.green"));
        break;
      case "error":
        this.iconPath = new vscode.ThemeIcon("error", new vscode.ThemeColor("charts.red"));
        break;
      default:
        this.iconPath = new vscode.ThemeIcon("cloud-download");
    }
    this.contextValue = "downloadStatus";
  }
}

class PaperNode extends vscode.TreeItem {
  constructor(report: AnalysisReport) {
    const title = report.extracted_content.title || "Untitled Paper";
    const score = report.review
      ? ` · score ${report.review.overall_score.toFixed(2)}`
      : "";
    super(`${title}${score}`, vscode.TreeItemCollapsibleState.Collapsed);
    this.iconPath = new vscode.ThemeIcon("book");
    this.contextValue = "paper";
    this.tooltip = report.extracted_content.authors.join(", ");
  }
}

class EquationNode extends vscode.TreeItem {
  readonly equationId: string;
  constructor(eq: { id: string; label: string | null; latex: string; section: string }) {
    super(
      `${eq.label ?? eq.id} · §${eq.section}`,
      vscode.TreeItemCollapsibleState.None
    );
    this.equationId = eq.id;
    this.description = eq.latex.substring(0, 60);
    this.iconPath = new vscode.ThemeIcon("symbol-operator");
    this.contextValue = "equation";
    this.command = {
      command: "researchAnalyser.openPanel",
      title: "Open Panel",
      arguments: [],
    };
  }
}

class SpecSectionNode extends vscode.TreeItem {
  constructor(item: CoverageItem) {
    const icon = item.implemented ? "✓" : "○";
    super(
      `${icon} §${item.sectionRef} ${item.sectionTitle}`,
      vscode.TreeItemCollapsibleState.None
    );
    this.iconPath = item.implemented
      ? new vscode.ThemeIcon("pass", new vscode.ThemeColor("charts.green"))
      : new vscode.ThemeIcon("circle-outline");
    this.contextValue = "specSection";
    this.tooltip = item.implemented
      ? `Implemented in ${item.locations.length} location(s)`
      : "Not yet implemented";
  }
}

class InfoNode extends vscode.TreeItem {
  constructor(label: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon("info");
  }
}

class ActionNode extends vscode.TreeItem {
  constructor(
    label: string,
    commandId: string,
    icon: string,
    description?: string,
  ) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
    this.contextValue = "action";
    this.command = { command: commandId, title: label };
    if (description) {
      this.description = description;
    }
  }
}

export class ResearchTreeDataProvider
  implements vscode.TreeDataProvider<TreeItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _coverageItems: CoverageItem[] = [];
  private _downloadState: DownloadState = "idle";
  private _downloadMessage = "";

  constructor(private readonly _store: ReportStore) {
    _store.onDidChange(() => this._onDidChangeTreeData.fire());
  }

  /** Update the download status shown in the sidebar tree. */
  setDownloadStatus(state: DownloadState, message?: string): void {
    this._downloadState = state;
    this._downloadMessage = message ?? "";
    this._onDidChangeTreeData.fire();
  }

  updateCoverage(items: CoverageItem[]): void {
    this._coverageItems = items;
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TreeItem): TreeItem[] {
    const state = this._store.state;

    if (!element) {
      // ── Download status node (always shows at the top when active) ──
      const rootItems: TreeItem[] = [];
      if (this._downloadState !== "idle") {
        rootItems.push(new DownloadStatusNode(this._downloadState, this._downloadMessage));
      }

      if (state.status === "empty") {
        if (rootItems.length === 0) {
          return [];  // truly empty → shows viewsWelcome action buttons
        }
        // Download status is active — viewsWelcome won't show, so add action nodes manually
        rootItems.push(new ActionNode(
          "Analyse Paper",
          "researchAnalyser.analyse",
          "search",
          "arXiv / URL / DOI / PDF"
        ));
        rootItems.push(new ActionNode(
          "Fetch Paper",
          "researchAnalyser.fetchPaper",
          "cloud-download",
          "arXiv / URL"
        ));
        rootItems.push(new ActionNode(
          "Text → Diagrams",
          "researchAnalyser.textToDiagrams",
          "type-hierarchy",
          "Beautiful Mermaid / PaperBanana"
        ));
        rootItems.push(new ActionNode(
          "Generate Peer Review",
          "researchAnalyser.generateReview",
          "comment-discussion",
          "Stanford agentic scoring"
        ));
        rootItems.push(new ActionNode(
          "Start Backend Server",
          "researchAnalyser.startServer",
          "server",
        ));
        rootItems.push(new ActionNode(
          "Download MonkeyOCR Offline",
          "researchAnalyser.downloadMonkeyOcr",
          "desktop-download",
        ));
        rootItems.push(new ActionNode(
          "Open Settings & API Keys",
          "researchAnalyser.openSettings",
          "gear",
        ));
        return rootItems;
      }
      if (state.status === "loading") {
        rootItems.push(new InfoNode(`Analysing: ${state.source}…`));
        return rootItems;
      }
      if (state.status === "error") {
        rootItems.push(new InfoNode(`Error: ${state.message}`));
        return rootItems;
      }
      // loaded
      rootItems.push(new PaperNode(state.report));

      // ── Quick-action nodes (always visible below the report) ─────
      rootItems.push(new ActionNode(
        "New Analysis",
        "researchAnalyser.analyse",
        "search",
        "arXiv / URL / DOI / PDF"
      ));
      rootItems.push(new ActionNode(
        "Text → Diagrams",
        "researchAnalyser.textToDiagrams",
        "type-hierarchy",
        "Beautiful Mermaid / PaperBanana"
      ));
      rootItems.push(new ActionNode(
        "Generate Peer Review",
        "researchAnalyser.generateReview",
        "comment-discussion",
        "Stanford agentic scoring"
      ));
      rootItems.push(new ActionNode(
        "Configure API Keys",
        "researchAnalyser.openSettings",
        "gear",
      ));

      return rootItems;
    }

    if (state.status !== "loaded") { return []; }
    const report = state.report;

    if (element instanceof PaperNode) {
      const nodes: TreeItem[] = [];
      // Equations group
      const eqGroup = new vscode.TreeItem(
        `Equations (${report.extracted_content.equations.length})`,
        vscode.TreeItemCollapsibleState.Collapsed
      );
      eqGroup.iconPath = new vscode.ThemeIcon("symbol-operator");
      (eqGroup as unknown as { _groupType: string })._groupType = "equations";

      // Spec sections group
      const secGroup = new vscode.TreeItem(
        `Spec Sections (${report.extracted_content.sections.length})`,
        vscode.TreeItemCollapsibleState.Collapsed
      );
      secGroup.iconPath = new vscode.ThemeIcon("list-tree");
      (secGroup as unknown as { _groupType: string })._groupType = "sections";

      nodes.push(eqGroup as unknown as TreeItem);
      nodes.push(secGroup as unknown as TreeItem);
      return nodes;
    }

    // Group children
    const groupType = (element as unknown as { _groupType?: string })._groupType;
    if (groupType === "equations") {
      return report.extracted_content.equations.map((eq) => new EquationNode(eq));
    }
    if (groupType === "sections") {
      if (this._coverageItems.length > 0) {
        return this._coverageItems.map((ci) => new SpecSectionNode(ci));
      }
      return report.extracted_content.sections.map(
        (s) =>
          new SpecSectionNode({
            sectionRef: s.section_number,
            sectionTitle: s.title,
            implemented: false,
            locations: [],
          })
      );
    }

    return [];
  }
}
