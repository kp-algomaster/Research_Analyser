"""Diagram generation using PaperBanana."""

from __future__ import annotations

import asyncio
import logging
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
    1. Retriever - Selects 10 most relevant reference examples
    2. Planner - Translates text into visual description
    3. Stylist - Refines for aesthetics matching target venue
    4. Visualizer - Renders descriptions into images (3 rounds)
    5. Critic - Evaluates output against source text
    """

    def __init__(
        self,
        provider: str = "google",
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
        self._pipeline = None

    def _load_pipeline(self):
        """Lazy-load the PaperBanana pipeline."""
        if self._pipeline is not None:
            return

        try:
            from paperbanana import PaperBananaPipeline
            from paperbanana.core.config import Settings

            settings = Settings(
                vlm_provider=self.provider,
                vlm_model=self.vlm_model,
                image_provider=f"{self.provider}_imagen",
                image_model=self.image_model,
                optimize_inputs=self.optimize_inputs,
                auto_refine=self.auto_refine,
            )

            self._pipeline = PaperBananaPipeline(settings=settings)
            logger.info(f"Loaded PaperBanana pipeline with {self.provider} provider")

        except ImportError:
            raise DiagramError(
                "PaperBanana is not installed. Install with: pip install paperbanana"
            )
        except Exception as e:
            raise DiagramError(f"Failed to initialize PaperBanana: {e}")

    async def generate(
        self,
        content: ExtractedContent,
        diagram_types: list[str] | None = None,
        auto_refine: bool = True,
    ) -> list[GeneratedDiagram]:
        """Generate diagrams from extracted paper content.

        Identifies relevant sections for each diagram type and runs
        the PaperBanana pipeline to generate publication-quality diagrams.
        """
        if diagram_types is None:
            diagram_types = ["methodology"]

        self.output_dir.mkdir(parents=True, exist_ok=True)
        diagrams = []

        tasks = []
        for dtype in diagram_types:
            match dtype:
                case "methodology":
                    tasks.append(self.generate_methodology(content))
                case "architecture":
                    tasks.append(self.generate_architecture(content))
                case "results":
                    tasks.append(self.generate_results_plot(content))
                case _:
                    logger.warning(f"Unknown diagram type: {dtype}")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Diagram generation failed: {result}")
            else:
                diagrams.append(result)

        return diagrams

    async def generate_methodology(self, content: ExtractedContent) -> GeneratedDiagram:
        """Generate methodology overview diagram."""
        # Find methodology-related sections
        method_text = self._find_section_content(
            content, ["method", "approach", "framework", "model", "proposed"]
        )

        if not method_text:
            method_text = content.abstract or content.full_text[:2000]

        try:
            self._load_pipeline()
            from paperbanana import GenerationInput
            from paperbanana import DiagramType as PBDiagramType

            result = await self._pipeline.generate(
                GenerationInput(
                    source_context=method_text,
                    communicative_intent=f"Overview of the methodology in: {content.title}",
                    diagram_type=PBDiagramType.METHODOLOGY,
                )
            )

            output_path = self.output_dir / f"methodology.{self.output_format}"
            # Copy result image to output directory
            if result.image_path:
                import shutil
                shutil.copy2(result.image_path, output_path)

            return GeneratedDiagram(
                diagram_type="methodology",
                image_path=str(output_path),
                caption=f"Methodology overview: {content.title}",
                source_context=method_text[:500],
                iterations=self.max_iterations,
                format=self.output_format,
            )

        except Exception as e:
            logger.warning(f"Methodology diagram generation failed, using fallback: {e}")
            return self._generate_fallback_diagram(
                diagram_type="methodology",
                title=content.title,
                source_context=method_text,
                stats={
                    "sections": len(content.sections),
                    "equations": len(content.equations),
                    "tables": len(content.tables),
                    "figures": len(content.figures),
                },
            )

    async def generate_architecture(self, content: ExtractedContent) -> GeneratedDiagram:
        """Generate architecture diagram."""
        arch_text = self._find_section_content(
            content, ["architecture", "model", "system", "design", "structure"]
        )

        if not arch_text:
            arch_text = content.abstract or content.full_text[:2000]

        try:
            self._load_pipeline()
            from paperbanana import GenerationInput
            from paperbanana import DiagramType as PBDiagramType

            result = await self._pipeline.generate(
                GenerationInput(
                    source_context=arch_text,
                    communicative_intent=f"Architecture of the system in: {content.title}",
                    diagram_type=PBDiagramType.METHODOLOGY,
                )
            )

            output_path = self.output_dir / f"architecture.{self.output_format}"
            if result.image_path:
                import shutil
                shutil.copy2(result.image_path, output_path)

            return GeneratedDiagram(
                diagram_type="architecture",
                image_path=str(output_path),
                caption=f"Architecture overview: {content.title}",
                source_context=arch_text[:500],
                iterations=self.max_iterations,
                format=self.output_format,
            )

        except Exception as e:
            logger.warning(f"Architecture diagram generation failed, using fallback: {e}")
            return self._generate_fallback_diagram(
                diagram_type="architecture",
                title=content.title,
                source_context=arch_text,
                stats={
                    "sections": len(content.sections),
                    "equations": len(content.equations),
                    "tables": len(content.tables),
                    "figures": len(content.figures),
                },
            )

    async def generate_results_plot(
        self, content: ExtractedContent, data: Optional[dict] = None
    ) -> GeneratedDiagram:
        """Generate results visualization plot."""
        results_text = self._find_section_content(
            content, ["results", "experiments", "evaluation", "performance"]
        )

        if not results_text:
            results_text = content.abstract or content.full_text[:2000]

        try:
            self._load_pipeline()
            from paperbanana import GenerationInput
            from paperbanana import DiagramType as PBDiagramType

            result = await self._pipeline.generate(
                GenerationInput(
                    source_context=results_text,
                    communicative_intent=f"Key results visualization: {content.title}",
                    diagram_type=PBDiagramType.RESULTS
                    if hasattr(PBDiagramType, "RESULTS")
                    else PBDiagramType.METHODOLOGY,
                )
            )

            output_path = self.output_dir / f"results_plot.{self.output_format}"
            if result.image_path:
                import shutil
                shutil.copy2(result.image_path, output_path)

            return GeneratedDiagram(
                diagram_type="results",
                image_path=str(output_path),
                caption=f"Results visualization: {content.title}",
                source_context=results_text[:500],
                iterations=self.max_iterations,
                format=self.output_format,
            )

        except Exception as e:
            logger.warning(f"Results diagram generation failed, using fallback: {e}")
            return self._generate_fallback_diagram(
                diagram_type="results",
                title=content.title,
                source_context=results_text,
                stats={
                    "sections": len(content.sections),
                    "equations": len(content.equations),
                    "tables": len(content.tables),
                    "figures": len(content.figures),
                },
            )

    def _generate_fallback_diagram(
        self,
        diagram_type: str,
        title: str,
        source_context: str,
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
                (x - 1.1, y - 0.9),
                2.2,
                1.8,
                boxstyle="round,pad=0.2",
                linewidth=1.5,
                edgecolor="#1f2937",
                facecolor="#e5e7eb",
            )
            ax.add_patch(box)
            ax.text(x, y, wrapped, ha="center", va="center", fontsize=10, fontweight="bold")

            detail = self._stage_detail(label)
            ax.text(x, y - 1.35, detail, ha="center", va="top", fontsize=8.5, color="#475569")

        for i in range(len(x_positions) - 1):
            start = (x_positions[i] + 1.1, y)
            end = (x_positions[i + 1] - 1.1, y)
            ax.annotate(
                "",
                xy=end,
                xytext=start,
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

        ax.text(8, 9.2, f"{diagram_type.title()} Overview", ha="center", va="center", fontsize=19, fontweight="bold")
        ax.text(8, 8.75, short_title, ha="center", va="center", fontsize=11)
        ax.text(8, 1.35, stats_line, ha="center", va="center", fontsize=10, color="#334155")
        if subtitle:
            ax.text(8, 0.85, subtitle, ha="center", va="center", fontsize=8.5, color="#4b5563")

        ax.text(
            8,
            2.2,
            "Flow: left-to-right pipeline from source ingestion to validated outputs",
            ha="center",
            va="center",
            fontsize=9,
            color="#334155",
        )

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
        )

    def _derive_fallback_stages(self, source_context: str) -> list[str]:
        """Infer a richer flow from context keywords for fallback diagrams."""
        context = source_context.lower()
        stages = ["Paper Input"]

        if any(token in context for token in ["lagrangian", "finite element", "tl-fea", "framework"]):
            stages.append("TL-FEA Formulation")
        else:
            stages.append("Method Formulation")

        if any(token in context for token in ["constraint", "kinematic", "multibody"]):
            stages.append("Kinematic Constraints")
        else:
            stages.append("Core Dynamics")

        if any(token in context for token in ["contact", "friction", "collision"]):
            stages.append("Contact & Friction")
        elif any(token in context for token in ["experiment", "evaluation", "results"]):
            stages.append("Evaluation")
        else:
            stages.append("Numerical Solution")

        stages.append("Outputs & Analysis")
        return stages[:5]

    def _stage_detail(self, stage_label: str) -> str:
        """Short explanatory detail for each fallback stage."""
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

    def _find_section_content(
        self, content: ExtractedContent, keywords: list[str]
    ) -> str:
        """Find section content matching keywords."""
        matching_sections = []
        for section in content.sections:
            title_lower = section.title.lower()
            if any(kw in title_lower for kw in keywords):
                matching_sections.append(section.content)

        if matching_sections:
            return "\n\n".join(matching_sections)
        return ""
