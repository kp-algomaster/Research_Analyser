"""Diagram generation using PaperBanana (Retriever → Planner → Stylist → Visualizer → Critic)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import textwrap
from pathlib import Path
from typing import Optional

from research_analyser.exceptions import DiagramError
from research_analyser.models import (
    DiagramType,
    ExtractedContent,
    GeneratedDiagram,
)

logger = logging.getLogger(__name__)


class DiagramGenerator:
    """Generate publication-quality diagrams using PaperBanana.

    PaperBanana pipeline stages:
    1. Retriever  — selects relevant reference examples
    2. Planner    — translates text into a visual description
    3. Stylist    — refines for aesthetics / target venue
    4. Visualizer — renders to image (N iterations)
    5. Critic     — evaluates output and requests revisions

    Falls back to a local matplotlib diagram if PaperBanana or the API key
    is unavailable.
    """

    def __init__(
        self,
        provider: str = "gemini",
        vlm_model: str = "gemini-2.0-flash",
        image_model: str = "gemini-3-pro-image-preview",
        optimize_inputs: bool = True,
        auto_refine: bool = True,
        max_iterations: int = 3,
        output_format: str = "png",
        output_dir: Optional[str] = None,
    ):
        self.provider = provider
        self.vlm_model = vlm_model
        self.image_model = image_model
        self.optimize_inputs = optimize_inputs
        self.auto_refine = auto_refine
        self.max_iterations = max_iterations
        self.output_format = output_format
        self.output_dir = Path(output_dir) if output_dir else Path("./output/diagrams")

    # ── PaperBanana pipeline ───────────────────────────────────────────────────

    def _make_pipeline(self, diagram_type: str):
        """Create a fresh PaperBananaPipeline for each diagram call.

        A fresh instance is required because PaperBanana assigns a single
        run_id at __init__ time and writes all generate() outputs into the
        same directory/filename.  Re-using one pipeline across concurrent
        generate() calls causes the second result to overwrite the first.
        """
        try:
            from paperbanana import PaperBananaPipeline
            from paperbanana.core.config import Settings
        except ImportError as e:
            raise DiagramError(
                "PaperBanana is not installed. "
                "Clone and install it: git clone https://github.com/llmsresearch/paperbanana.git "
                "&& pip install -e '.[dev,openai,google]'"
            ) from e

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise DiagramError(
                "GOOGLE_API_KEY is not set. "
                "Add your Google API key in the Configuration page."
            )

        # Give each diagram type its own subdirectory so concurrent runs
        # never share an output path.
        subdir = self.output_dir / diagram_type

        settings = Settings(
            vlm_provider=self.provider,
            vlm_model=self.vlm_model,
            image_provider="google_imagen",
            image_model=self.image_model,
            google_api_key=api_key,
            output_dir=str(subdir),
            refinement_iterations=self.max_iterations,
        )

        logger.info(
            "PaperBanana pipeline created for '%s' (vlm=%s, image=%s)",
            diagram_type, self.vlm_model, self.image_model,
        )
        return PaperBananaPipeline(settings=settings)

    # ── Public generate API ────────────────────────────────────────────────────

    async def generate(
        self,
        content: ExtractedContent,
        diagram_types: list[str] | None = None,
        auto_refine: bool = True,
        on_progress: Optional[callable] = None,
    ) -> list[GeneratedDiagram]:
        """Generate diagrams from extracted paper content.

        Args:
            on_progress: Optional ``fn(dtype: str, status: str)`` called
                before and after each diagram so the caller can show live
                status (e.g. "🔄 Generating…", "✓ Done", "✗ Failed").
        """
        if diagram_types is None:
            diagram_types = ["methodology"]

        self.output_dir.mkdir(parents=True, exist_ok=True)

        def _report(dtype: str, status: str) -> None:
            if on_progress:
                try:
                    on_progress(dtype, status)
                except Exception:
                    pass

        async def _run_one(dtype: str):
            _report(dtype, "🔄 Generating…")
            try:
                match dtype:
                    case "methodology":
                        result = await self.generate_methodology(content)
                    case "architecture":
                        result = await self.generate_architecture(content)
                    case "results":
                        result = await self.generate_results_plot(content)
                    case _:
                        logger.warning("Unknown diagram type: %s", dtype)
                        _report(dtype, "⚠️ Unknown type")
                        return None
                is_fb = getattr(result, "is_fallback", False)
                _report(dtype, "✓ Done (fallback)" if is_fb else "✓ Done")
                return result
            except Exception as exc:
                _report(dtype, "✗ Failed")
                logger.error("Diagram generation failed for %s: %s", dtype, exc)
                raise

        # Mark all as queued upfront so the UI shows them immediately
        for dtype in diagram_types:
            _report(dtype, "⏳ Queued")

        results = await asyncio.gather(
            *[_run_one(dtype) for dtype in diagram_types],
            return_exceptions=True,
        )
        diagrams = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("Diagram generation failed: %s", result)
            elif result is not None:
                diagrams.append(result)
        return diagrams

    async def generate_methodology(self, content: ExtractedContent) -> GeneratedDiagram:
        """Generate methodology overview diagram."""
        method_text = self._find_section_content(
            content, ["method", "approach", "framework", "model", "proposed"]
        ) or content.abstract or content.full_text[:2000]

        return await self._run_pipeline(
            diagram_type="methodology",
            content=content,
            context=method_text,
            communicative_intent=f"Methodology pipeline and key steps of: {content.title}",
            pb_diagram_type="METHODOLOGY",
        )

    async def generate_architecture(self, content: ExtractedContent) -> GeneratedDiagram:
        """Generate architecture diagram."""
        arch_text = self._find_section_content(
            content, ["architecture", "model", "system", "design", "structure"]
        ) or content.abstract or content.full_text[:2000]

        return await self._run_pipeline(
            diagram_type="architecture",
            content=content,
            context=arch_text,
            communicative_intent=f"System architecture and component relationships of: {content.title}",
            pb_diagram_type="METHODOLOGY",  # PaperBanana v0.1 only has METHODOLOGY + STATISTICAL_PLOT
        )

    async def generate_results_plot(
        self, content: ExtractedContent, data: Optional[dict] = None
    ) -> GeneratedDiagram:
        """Generate results visualization diagram."""
        results_text = self._find_section_content(
            content, ["results", "experiments", "evaluation", "performance"]
        ) or content.abstract or content.full_text[:2000]

        return await self._run_pipeline(
            diagram_type="results",
            content=content,
            context=results_text,
            communicative_intent=f"Key results and performance metrics of: {content.title}",
            pb_diagram_type="STATISTICAL_PLOT",
        )

    # ── Core pipeline runner ───────────────────────────────────────────────────

    async def _run_pipeline(
        self,
        diagram_type: str,
        content: ExtractedContent,
        context: str,
        communicative_intent: str,
        pb_diagram_type: str = "METHODOLOGY",
    ) -> GeneratedDiagram:
        """Run the PaperBanana pipeline; fall back to matplotlib on failure."""
        output_path = self.output_dir / f"{diagram_type}.{self.output_format}"

        try:
            from paperbanana import GenerationInput, DiagramType as PBDiagramType

            pipeline = self._make_pipeline(diagram_type)
            pb_dtype = getattr(PBDiagramType, pb_diagram_type, PBDiagramType.METHODOLOGY)

            result = await pipeline.generate(
                GenerationInput(
                    source_context=context[:4000],
                    communicative_intent=communicative_intent,
                    diagram_type=pb_dtype,
                )
            )

            # Copy PaperBanana's output to our standardised path.
            # result.image_path lives inside the per-type subdir created by
            # _make_pipeline(); we copy it to the top-level output_dir so
            # the rest of the app always finds it at a predictable location.
            src = Path(result.image_path)
            if src.exists():
                shutil.copy2(src, output_path)
            else:
                raise DiagramError(f"PaperBanana output file not found: {src}")

            return GeneratedDiagram(
                diagram_type=diagram_type,
                image_path=str(output_path),
                caption=f"{diagram_type.title()} diagram: {content.title}",
                source_context=context[:500],
                iterations=len(result.iterations) if result.iterations else 1,
                format=self.output_format,
            )

        except Exception as exc:
            logger.warning(
                "%s diagram (PaperBanana) failed — using matplotlib fallback. Error: %s",
                diagram_type, exc,
            )
            return self._generate_fallback_diagram(
                diagram_type=diagram_type,
                title=content.title,
                source_context=context,
                error=str(exc),
                stats={
                    "sections": len(content.sections),
                    "equations": len(content.equations),
                    "tables": len(content.tables),
                    "figures": len(content.figures),
                },
            )

    # ── Matplotlib fallback ────────────────────────────────────────────────────

    def _generate_fallback_diagram(
        self,
        diagram_type: str,
        title: str,
        source_context: str,
        error: str = "",
        stats: Optional[dict] = None,
    ) -> GeneratedDiagram:
        """Generate a simple local overview diagram when PaperBanana is unavailable."""
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch

        output_path = self.output_dir / f"{diagram_type}.{self.output_format}"

        fig, ax = plt.subplots(figsize=(16, 9))
        ax.set_xlim(0, 16)
        ax.set_ylim(0, 10)
        ax.axis("off")

        stages = self._derive_fallback_stages(source_context)
        x_positions = [2.0, 5.0, 8.0, 11.0, 14.0]
        y = 5.2

        for x, label in zip(x_positions, stages):
            wrapped = "\n".join(textwrap.wrap(label, width=18))
            box = FancyBboxPatch(
                (x - 1.1, y - 0.9), 2.2, 1.8,
                boxstyle="round,pad=0.2",
                linewidth=1.5, edgecolor="#1f2937", facecolor="#e5e7eb",
            )
            ax.add_patch(box)
            ax.text(x, y, wrapped, ha="center", va="center", fontsize=10, fontweight="bold")
            ax.text(x, y - 1.35, self._stage_detail(label),
                    ha="center", va="top", fontsize=8.5, color="#475569")

        for i in range(len(x_positions) - 1):
            ax.annotate(
                "", xy=(x_positions[i + 1] - 1.1, y),
                xytext=(x_positions[i] + 1.1, y),
                arrowprops={"arrowstyle": "->", "lw": 1.5, "color": "#374151"},
            )

        short_title = title if len(title) <= 110 else title[:107] + "..."
        subtitle = source_context.strip().replace("\n", " ")
        subtitle = subtitle[:220] + "..." if len(subtitle) > 220 else subtitle
        stats = stats or {}
        stats_line = (
            f"Sections: {stats.get('sections', 0)} | "
            f"Equations: {stats.get('equations', 0)} | "
            f"Tables: {stats.get('tables', 0)} | "
            f"Figures: {stats.get('figures', 0)}"
        )

        ax.text(8, 9.2, f"{diagram_type.title()} Overview",
                ha="center", fontsize=19, fontweight="bold")
        ax.text(8, 8.75, short_title, ha="center", fontsize=11)
        ax.text(8, 1.35, stats_line, ha="center", fontsize=10, color="#334155")
        if subtitle:
            ax.text(8, 0.85, subtitle, ha="center", fontsize=8.5, color="#4b5563")
        ax.text(8, 2.2,
                "Flow: left-to-right pipeline from source ingestion to validated outputs",
                ha="center", fontsize=9, color="#334155")

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

        return GeneratedDiagram(
            diagram_type=diagram_type,
            image_path=str(output_path),
            caption=f"{diagram_type.title()} overview (local fallback): {title}",
            source_context=source_context[:500],
            iterations=1,
            format=self.output_format,
            is_fallback=True,
            error=error,
        )

    def _derive_fallback_stages(self, source_context: str) -> list[str]:
        context = source_context.lower()
        stages = ["Paper Input"]
        if any(t in context for t in ["lagrangian", "finite element", "tl-fea", "framework"]):
            stages.append("TL-FEA Formulation")
        else:
            stages.append("Method Formulation")
        if any(t in context for t in ["constraint", "kinematic", "multibody"]):
            stages.append("Kinematic Constraints")
        else:
            stages.append("Core Dynamics")
        if any(t in context for t in ["contact", "friction", "collision"]):
            stages.append("Contact & Friction")
        elif any(t in context for t in ["experiment", "evaluation", "results"]):
            stages.append("Evaluation")
        else:
            stages.append("Numerical Solution")
        stages.append("Outputs & Analysis")
        return stages[:5]

    def _stage_detail(self, stage_label: str) -> str:
        mapping = {
            "Paper Input": "arXiv/PDF ingestion",
            "TL-FEA Formulation": "state vars + element model",
            "Method Formulation": "problem statement + setup",
            "Kinematic Constraints": "constraints and coupling",
            "Core Dynamics": "forces and motion update",
            "Contact & Friction": "interaction and stability",
            "Evaluation": "metrics and validation",
            "Numerical Solution": "solver and convergence",
            "Outputs & Analysis": "report, equations, diagrams",
        }
        return mapping.get(stage_label, "analysis stage")

    def _find_section_content(self, content: ExtractedContent, keywords: list[str]) -> str:
        matching = [
            s.content for s in content.sections
            if any(kw in s.title.lower() for kw in keywords)
        ]
        return "\n\n".join(matching) if matching else ""
