"""Main orchestrator: coordinate all modules in the analysis pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from research_analyser.config import Config
from research_analyser.diagram_generator import DiagramGenerator
from research_analyser.exceptions import ResearchAnalyserError
from research_analyser.input_handler import InputHandler
from research_analyser.models import (
    AnalysisOptions,
    AnalysisReport,
    KeyPoint,
    PaperInput,
    PaperSummary,
    ReportMetadata,
    SourceType,
)
from research_analyser.ocr_engine import OCREngine
from research_analyser.report_generator import ReportGenerator
from research_analyser.reviewer import PaperReviewer

logger = logging.getLogger(__name__)


class ResearchAnalyser:
    """Main orchestrator for the research paper analysis pipeline.

    Coordinates:
    - InputHandler: resolve PDFs from URLs, arXiv, DOIs
    - OCREngine: extract content via MonkeyOCR 1.5
    - DiagramGenerator: generate diagrams via PaperBanana
    - PaperReviewer: generate peer review via agentic workflow
    - ReportGenerator: assemble structured output reports
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load()

        self.input_handler = InputHandler(
            temp_dir=self.config.app.temp_dir,
        )
        self.ocr_engine = OCREngine(
            model_name=self.config.ocr.model,
            device=self.config.ocr.device,
        )
        self.diagram_generator = DiagramGenerator(
            provider=self.config.diagrams.provider,
            vlm_model=self.config.diagrams.vlm_model,
            image_model=self.config.diagrams.image_model,
            optimize_inputs=self.config.diagrams.optimize_inputs,
            auto_refine=self.config.diagrams.auto_refine,
            max_iterations=self.config.diagrams.max_iterations,
            output_format=self.config.diagrams.output_format,
            output_dir=str(Path(self.config.app.output_dir) / "diagrams"),
        )
        self.reviewer = PaperReviewer(
            llm_provider=self.config.review.llm_provider,
            model=self.config.review.model,
            tavily_api_key=self.config.tavily_api_key,
            openai_api_key=self.config.openai_api_key,
        )
        self.report_generator = ReportGenerator()

    async def analyse(
        self,
        source: str,
        source_type: Optional[str] = None,
        options: Optional[AnalysisOptions] = None,
    ) -> AnalysisReport:
        """Run complete analysis pipeline.

        Args:
            source: PDF file path, URL, arXiv ID, or DOI
            source_type: Override auto-detection of source type
            options: Analysis configuration options

        Returns:
            Complete AnalysisReport with all analysis results
        """
        start_time = time.time()
        options = options or AnalysisOptions()

        # 1. Detect source type
        if source_type:
            detected_type = SourceType(source_type)
        else:
            detected_type = self.input_handler.detect_source_type(source)

        paper_input = PaperInput(
            source_type=detected_type,
            source_value=source,
            analysis_options=options,
        )

        logger.info(f"Analysing paper: {source} (type: {detected_type.value})")

        # 2. Resolve to local PDF
        pdf_path = await self.input_handler.resolve(paper_input)
        logger.info(f"Resolved to: {pdf_path}")

        # 3. Extract content via MonkeyOCR
        logger.info("Extracting content with MonkeyOCR...")
        content = await self.ocr_engine.extract(pdf_path)
        logger.info(
            f"Extracted: {len(content.equations)} equations, "
            f"{len(content.tables)} tables, {len(content.figures)} figures"
        )

        # 4. Run analysis tasks in parallel
        tasks = []
        if options.generate_diagrams:
            tasks.append(
                self.diagram_generator.generate(content, options.diagram_types)
            )
        if options.generate_review:
            tasks.append(
                self.reviewer.review(content, paper_input.target_venue)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        diagrams = []
        review = None
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Analysis task failed: {result}")
            elif isinstance(result, list):
                diagrams = result
            else:
                review = result

        # 5. Generate summary
        summary = PaperSummary(
            one_sentence=f"Analysis of '{content.title}'",
            abstract_summary=content.abstract[:500] if content.abstract else "",
            methodology_summary=self._extract_methodology_summary(content),
            results_summary=self._extract_results_summary(content),
            conclusions=self._extract_conclusions(content),
        )

        # 6. Extract key points
        key_points = self._extract_key_points(content, review)

        # 7. Assemble report
        elapsed = time.time() - start_time
        metadata = ReportMetadata(
            ocr_model=self.config.ocr.model,
            diagram_provider=self.config.diagrams.provider,
            review_model=self.config.review.model,
            processing_time_seconds=elapsed,
        )

        report = AnalysisReport(
            paper_input=paper_input,
            extracted_content=content,
            review=review,
            diagrams=diagrams,
            summary=summary,
            key_points=key_points,
            metadata=metadata,
        )

        # 8. Save outputs
        output_dir = Path(self.config.app.output_dir)
        self.report_generator.save_all(report, output_dir)
        logger.info(f"Analysis complete in {elapsed:.1f}s. Output: {output_dir}")

        return report

    def _extract_methodology_summary(self, content) -> str:
        """Extract methodology summary from sections."""
        for section in content.sections:
            if any(
                kw in section.title.lower()
                for kw in ["method", "approach", "proposed", "framework"]
            ):
                return section.content[:500]
        if content.abstract:
            return content.abstract[:500]
        return ""

    def _extract_results_summary(self, content) -> str:
        """Extract results summary from sections."""
        for section in content.sections:
            if any(
                kw in section.title.lower()
                for kw in ["results", "experiments", "evaluation"]
            ):
                return section.content[:500]
        if content.full_text:
            return content.full_text[:500]
        return ""

    def _extract_conclusions(self, content) -> str:
        """Extract conclusions from sections."""
        for section in content.sections:
            if "conclusion" in section.title.lower():
                return section.content[:500]
        if content.abstract:
            return content.abstract[:500]
        return ""

    def _extract_key_points(self, content, review) -> list[KeyPoint]:
        """Extract key points from content and review."""
        points = []

        # From abstract
        if content.abstract:
            points.append(
                KeyPoint(
                    point=f"Paper presents: {content.title}",
                    evidence=content.abstract[:200],
                    section="Abstract",
                    importance="high",
                )
            )

        # From review strengths
        if review:
            for strength in review.strengths[:3]:
                points.append(
                    KeyPoint(
                        point=strength,
                        evidence="Identified by peer review analysis",
                        section="Review",
                        importance="high",
                    )
                )

        # From key equations
        display_eqs = [eq for eq in content.equations if not eq.is_inline]
        if display_eqs:
            points.append(
                KeyPoint(
                    point=f"Paper includes {len(display_eqs)} key equations/formulae",
                    evidence=f"First equation: {display_eqs[0].latex[:100]}",
                    section=display_eqs[0].section,
                    importance="medium",
                )
            )

        return points
