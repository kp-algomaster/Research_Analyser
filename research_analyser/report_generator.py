"""Report generation: assemble analysis components into structured outputs."""

from __future__ import annotations

import json
import logging
from html import escape
from datetime import datetime
from pathlib import Path

from research_analyser.models import AnalysisReport, Equation, KeyPoint
from research_analyser.reviewer import interpret_score

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Assemble all analysis components into structured output reports."""

    def _asset_path(self, raw_path: str, output_dir: Path) -> str:
        """Return a stable report-relative asset path for markdown/html embeds."""
        path = Path(raw_path)

        # Absolute path inside output dir -> make relative
        if path.is_absolute():
            try:
                return str(path.relative_to(output_dir))
            except ValueError:
                return str(path)

        # Relative path prefixed with output dir name -> strip it
        output_name = output_dir.name
        parts = path.parts
        if parts and parts[0] == output_name:
            return str(Path(*parts[1:]))

        return str(path)

    def generate_report(self, report: AnalysisReport, output_dir: Path | None = None) -> str:
        """Generate full markdown analysis report."""
        output_dir = output_dir or Path("./output")
        lines = []

        # YAML frontmatter
        lines.append("---")
        lines.append(f'title: "{report.extracted_content.title}"')
        lines.append(
            f"authors: [{', '.join(report.extracted_content.authors)}]"
        )
        lines.append(f"date_analysed: \"{report.metadata.analysed_at.isoformat()}\"")
        lines.append(f'source: "{report.paper_input.source_value}"')
        lines.append('tools: ["MonkeyOCR 1.5", "PaperBanana", "Agentic Reviewer"]')
        lines.append("---\n")

        # Title
        lines.append(f"# Analysis Report: {report.extracted_content.title}\n")

        # Summary
        if report.summary:
            lines.append("## Summary\n")
            lines.append(report.summary.one_sentence + "\n")
            lines.append(report.summary.abstract_summary + "\n")

        # Key Findings
        if report.key_points:
            lines.append("## Key Findings\n")
            for i, kp in enumerate(report.key_points, 1):
                lines.append(f"{i}. **{kp.point}**")
                lines.append(f"   - Evidence: {kp.evidence}")
                lines.append(f"   - Section: {kp.section}\n")

        # Key Equations
        if report.extracted_content.equations:
            lines.append("## Key Equations\n")
            display_eqs = [
                eq for eq in report.extracted_content.equations if not eq.is_inline
            ]
            for eq in display_eqs[:10]:
                label = f" ({eq.label})" if eq.label else ""
                lines.append(f"### {eq.id}{label}\n")
                lines.append(f"$$\n{eq.latex}\n$$\n")
                if eq.description:
                    lines.append(f"> {eq.description}\n")
                lines.append(f"*Section: {eq.section}*\n")

        # Methodology
        if report.summary:
            lines.append("## Methodology\n")
            lines.append(report.summary.methodology_summary + "\n")

        # Diagrams
        if report.diagrams:
            lines.append("## Generated Diagrams\n")
            for diagram in report.diagrams:
                diagram_path = self._asset_path(diagram.image_path, output_dir)
                lines.append(f"### {diagram.diagram_type.title()} Diagram\n")
                lines.append(f"![{diagram.caption}]({diagram_path})\n")
                lines.append(f"*{diagram.caption}*\n")

        # Peer Review
        if report.review:
            review = report.review
            decision = interpret_score(review.overall_score)
            lines.append("## Peer Review\n")
            lines.append(
                f"**Overall Score: {review.overall_score:.1f}/10** "
                f"({decision}) | Confidence: {review.confidence:.0f}/5\n"
            )

            # Dimensional scores
            lines.append("### Dimensional Scores\n")
            lines.append("| Dimension | Score | Weight |")
            lines.append("|-----------|-------|--------|")
            for name, dim in review.dimensions.items():
                pct = dim.weight / sum(d.weight for d in review.dimensions.values()) * 100
                lines.append(f"| {dim.name} | {dim.score:.1f}/4 | {pct:.1f}% |")
            lines.append("")

            # Strengths
            lines.append("### Strengths\n")
            for s in review.strengths:
                lines.append(f"- {s}")
            lines.append("")

            # Weaknesses
            lines.append("### Weaknesses\n")
            for w in review.weaknesses:
                lines.append(f"- {w}")
            lines.append("")

            # Suggestions
            if review.suggestions:
                lines.append("### Suggestions\n")
                for s in review.suggestions:
                    lines.append(f"- {s}")
                lines.append("")

            # Related Works
            if review.related_works:
                lines.append("### Related Work\n")
                for rw in review.related_works[:10]:
                    url = f" - [{rw.url}]({rw.url})" if rw.url else ""
                    lines.append(f"- **{rw.title}**{url}")
                lines.append("")

        # Results
        if report.summary:
            lines.append("## Results\n")
            lines.append(report.summary.results_summary + "\n")

            lines.append("## Conclusions\n")
            lines.append(report.summary.conclusions + "\n")

        # Tables
        if report.extracted_content.tables:
            lines.append("## Extracted Tables\n")
            for table in report.extracted_content.tables[:5]:
                if table.caption:
                    lines.append(f"### {table.caption}\n")
                lines.append(table.content + "\n")

        return "\n".join(lines)

    def generate_key_points(self, report: AnalysisReport) -> str:
        """Generate key points and equations summary markdown."""
        lines = []

        # YAML frontmatter
        lines.append("---")
        lines.append(f'paper_id: "{report.extracted_content.title}"')
        lines.append(f'extraction_model: "{report.metadata.ocr_model}"')
        lines.append(f'extraction_date: "{report.metadata.analysed_at.isoformat()}"')
        lines.append("---\n")

        lines.append(f"# Key Points: {report.extracted_content.title}\n")

        # Core contributions
        lines.append("## Core Contributions\n")
        high_points = [kp for kp in report.key_points if kp.importance == "high"]
        for i, kp in enumerate(high_points or report.key_points[:5], 1):
            lines.append(f"{i}. {kp.point}")
        lines.append("")

        # Equations & Formulae
        display_eqs = [
            eq for eq in report.extracted_content.equations if not eq.is_inline
        ]
        if display_eqs:
            lines.append("## Equations & Formulae\n")
            for eq in display_eqs[:15]:
                label = eq.label or eq.id
                lines.append(f"### {label}\n")
                lines.append(f"$$\n{eq.latex}\n$$\n")
                if eq.description:
                    lines.append(f"> **Description:** {eq.description}")
                lines.append(f"> **Section:** {eq.section}\n")

        # Summary statistics
        lines.append("## Document Statistics\n")
        lines.append(
            f"- **Sections:** {len(report.extracted_content.sections)}"
        )
        lines.append(
            f"- **Equations:** {len(report.extracted_content.equations)} "
            f"({len(display_eqs)} display, "
            f"{len(report.extracted_content.equations) - len(display_eqs)} inline)"
        )
        lines.append(f"- **Tables:** {len(report.extracted_content.tables)}")
        lines.append(f"- **Figures:** {len(report.extracted_content.figures)}")
        lines.append(
            f"- **References:** {len(report.extracted_content.references)}"
        )
        if report.review:
            lines.append(
                f"- **Review Score:** {report.review.overall_score:.1f}/10 "
                f"({interpret_score(report.review.overall_score)})"
            )
        lines.append("")

        return "\n".join(lines)

    def generate_spec_output(self, report: AnalysisReport) -> str:
        """Generate spec-driven output for downstream code generation.

        Machine-readable markdown with structured data for use
        in other applications or AI code generation tools.
        """
        lines = []

        lines.append("---")
        lines.append(f'title: "{report.extracted_content.title}"')
        lines.append(f'format: "spec-driven"')
        lines.append(f'version: "1.0"')
        lines.append("---\n")

        lines.append(f"# Spec Output: {report.extracted_content.title}\n")

        # Structured equations for code generation
        lines.append("## Equations (Machine-Readable)\n")
        lines.append("```json")
        equations_data = []
        for eq in report.extracted_content.equations:
            if not eq.is_inline:
                equations_data.append({
                    "id": eq.id,
                    "latex": eq.latex,
                    "label": eq.label,
                    "section": eq.section,
                    "description": eq.description,
                })
        lines.append(json.dumps(equations_data, indent=2))
        lines.append("```\n")

        # Key findings as structured data
        lines.append("## Key Findings (Structured)\n")
        lines.append("```json")
        findings = [
            {
                "finding": kp.point,
                "evidence": kp.evidence,
                "section": kp.section,
                "importance": kp.importance,
            }
            for kp in report.key_points
        ]
        lines.append(json.dumps(findings, indent=2))
        lines.append("```\n")

        # Review scores
        if report.review:
            lines.append("## Review Scores (Structured)\n")
            lines.append("```json")
            scores = {
                "overall": report.review.overall_score,
                "confidence": report.review.confidence,
                "dimensions": {
                    name: {"score": dim.score, "weight": dim.weight}
                    for name, dim in report.review.dimensions.items()
                },
                "decision": interpret_score(report.review.overall_score),
            }
            lines.append(json.dumps(scores, indent=2))
            lines.append("```\n")

        return "\n".join(lines)

    def generate_html_report(self, report: AnalysisReport, output_dir: Path | None = None) -> str:
        """Generate an HTML report with equations, diagrams, and figures."""
        output_dir = output_dir or Path("./output")
        title = escape(report.extracted_content.title)
        authors = ", ".join(escape(a) for a in report.extracted_content.authors) or "Unknown"
        analysed_at = escape(report.metadata.analysed_at.isoformat())
        source = escape(report.paper_input.source_value)

        parts: list[str] = []
        parts.append("<!doctype html>")
        parts.append("<html lang=\"en\">")
        parts.append("<head>")
        parts.append("<meta charset=\"utf-8\">")
        parts.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
        parts.append(f"<title>Analysis Report - {title}</title>")
        parts.append("<style>")
        parts.append(
            "body{font-family:Georgia,'Times New Roman',serif;max-width:1000px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#111827;background:#f9fafb;}"
            "h1,h2,h3{color:#0f172a;}"
            ".meta{background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:1rem;margin-bottom:1.5rem;}"
            ".card{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:1rem;margin:1rem 0;}"
            ".eq{background:#f8fafc;border-left:4px solid #94a3b8;padding:.8rem;margin:.8rem 0;}"
            ".muted{color:#475569;font-size:.95rem;}"
            "img{max-width:100%;height:auto;border:1px solid #d1d5db;border-radius:6px;background:#fff;}"
            "table{border-collapse:collapse;width:100%;}"
            "th,td{border:1px solid #d1d5db;padding:.45rem;text-align:left;}"
        )
        parts.append("</style>")
        # MathJax for LaTeX equations
        parts.append(
            "<script defer src=\"https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js\"></script>"
        )
        parts.append("</head>")
        parts.append("<body>")

        parts.append(f"<h1>Analysis Report: {title}</h1>")
        parts.append("<div class=\"meta\">")
        parts.append(f"<div><strong>Authors:</strong> {authors}</div>")
        parts.append(f"<div><strong>Analysed At:</strong> {analysed_at}</div>")
        parts.append(f"<div><strong>Source:</strong> {source}</div>")
        parts.append("</div>")

        if report.summary:
            parts.append("<h2>Summary</h2>")
            parts.append(f"<div class=\"card\"><p>{escape(report.summary.one_sentence)}</p>")
            if report.summary.abstract_summary:
                parts.append(f"<p>{escape(report.summary.abstract_summary)}</p>")
            parts.append("</div>")

        if report.key_points:
            parts.append("<h2>Key Findings</h2>")
            parts.append("<div class=\"card\"><ol>")
            for kp in report.key_points:
                parts.append(
                    f"<li><strong>{escape(kp.point)}</strong><br><span class=\"muted\">Evidence:</span> {escape(kp.evidence)}"
                    f"<br><span class=\"muted\">Section:</span> {escape(kp.section)}</li>"
                )
            parts.append("</ol></div>")

        display_eqs = [eq for eq in report.extracted_content.equations if not eq.is_inline]
        if display_eqs:
            parts.append("<h2>Key Equations</h2>")
            parts.append("<div class=\"card\">")
            for eq in display_eqs[:20]:
                label = f" ({escape(eq.label)})" if eq.label else ""
                parts.append(f"<h3>{escape(eq.id)}{label}</h3>")
                parts.append(f"<div class=\"eq\">\\[{eq.latex}\\]</div>")
                if eq.description:
                    parts.append(f"<p class=\"muted\">{escape(eq.description)}</p>")
                parts.append(f"<p class=\"muted\">Section: {escape(eq.section)}</p>")
            parts.append("</div>")

        if report.summary:
            parts.append("<h2>Methodology</h2>")
            parts.append(f"<div class=\"card\"><p>{escape(report.summary.methodology_summary)}</p></div>")

        if report.diagrams:
            parts.append("<h2>Generated Diagrams</h2>")
            for diagram in report.diagrams:
                diagram_path = self._asset_path(diagram.image_path, output_dir)
                parts.append("<div class=\"card\">")
                parts.append(f"<h3>{escape(diagram.diagram_type.title())}</h3>")
                parts.append(f"<img src=\"{escape(diagram_path)}\" alt=\"{escape(diagram.caption)}\">")
                parts.append(f"<p class=\"muted\">{escape(diagram.caption)}</p>")
                parts.append("</div>")

        paper_figures = [f for f in report.extracted_content.figures if f.image_path]
        if paper_figures:
            parts.append("<h2>Extracted Figures</h2>")
            for fig in paper_figures[:10]:
                figure_path = self._asset_path(fig.image_path or "", output_dir)
                parts.append("<div class=\"card\">")
                parts.append(f"<h3>{escape(fig.id)}</h3>")
                parts.append(f"<img src=\"{escape(figure_path)}\" alt=\"{escape(fig.caption or fig.id)}\">")
                if fig.caption:
                    parts.append(f"<p class=\"muted\">{escape(fig.caption)}</p>")
                parts.append("</div>")

        if report.summary:
            parts.append("<h2>Results</h2>")
            parts.append(f"<div class=\"card\"><p>{escape(report.summary.results_summary)}</p></div>")
            parts.append("<h2>Conclusions</h2>")
            parts.append(f"<div class=\"card\"><p>{escape(report.summary.conclusions)}</p></div>")

        if report.review:
            decision = interpret_score(report.review.overall_score)
            parts.append("<h2>Peer Review</h2>")
            parts.append("<div class=\"card\">")
            parts.append(
                f"<p><strong>Overall Score:</strong> {report.review.overall_score:.1f}/10 ({escape(decision)}) "
                f"| <strong>Confidence:</strong> {report.review.confidence:.1f}/5</p>"
            )
            parts.append("</div>")

        parts.append("</body>")
        parts.append("</html>")
        return "\n".join(parts)

    def save_all(self, report: AnalysisReport, output_dir: Path) -> None:
        """Save all outputs to directory structure."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Main report
        report_path = output_dir / "report.md"
        report_path.write_text(self.generate_report(report, output_dir=output_dir), encoding="utf-8")
        logger.info(f"Saved report to {report_path}")

        # Key points
        kp_path = output_dir / "key_points.md"
        kp_path.write_text(self.generate_key_points(report), encoding="utf-8")
        logger.info(f"Saved key points to {kp_path}")

        # Spec output
        spec_path = output_dir / "spec_output.md"
        spec_path.write_text(self.generate_spec_output(report), encoding="utf-8")
        logger.info(f"Saved spec output to {spec_path}")

        # HTML report
        html_path = output_dir / "report.html"
        html_path.write_text(
            self.generate_html_report(report, output_dir=output_dir),
            encoding="utf-8",
        )
        logger.info(f"Saved HTML report to {html_path}")

        # Review (if available)
        if report.review:
            review_path = output_dir / "review.md"
            review_text = report.review.raw_review
            review_path.write_text(review_text, encoding="utf-8")
            logger.info(f"Saved review to {review_path}")

        # Extracted content
        extracted_dir = output_dir / "extracted"
        extracted_dir.mkdir(exist_ok=True)

        # Full text
        (extracted_dir / "full_text.md").write_text(
            report.extracted_content.full_text, encoding="utf-8"
        )

        # Equations JSON
        equations_data = [
            {
                "id": eq.id,
                "latex": eq.latex,
                "type": "inline" if eq.is_inline else "display",
                "label": eq.label,
                "section": eq.section,
                "context": eq.context,
                "description": eq.description,
            }
            for eq in report.extracted_content.equations
        ]
        (extracted_dir / "equations.json").write_text(
            json.dumps(equations_data, indent=2), encoding="utf-8"
        )

        # Tables JSON
        tables_data = [
            {
                "id": t.id,
                "content": t.content,
                "caption": t.caption,
                "section": t.section,
            }
            for t in report.extracted_content.tables
        ]
        (extracted_dir / "tables.json").write_text(
            json.dumps(tables_data, indent=2), encoding="utf-8"
        )

        # Metadata
        metadata = {
            "title": report.extracted_content.title,
            "authors": report.extracted_content.authors,
            "source": report.paper_input.source_value,
            "source_type": report.paper_input.source_type.value,
            "analysed_at": report.metadata.analysed_at.isoformat(),
            "ocr_model": report.metadata.ocr_model,
            "diagram_provider": report.metadata.diagram_provider,
            "review_model": report.metadata.review_model,
            "num_equations": len(report.extracted_content.equations),
            "num_tables": len(report.extracted_content.tables),
            "num_figures": len(report.extracted_content.figures),
            "num_diagrams": len(report.diagrams),
            "review_score": report.review.overall_score if report.review else None,
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        logger.info(f"All outputs saved to {output_dir}")
