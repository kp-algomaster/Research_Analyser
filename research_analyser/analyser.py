"""Main orchestrator: coordinate all modules in the analysis pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from research_analyser.config import Config
from research_analyser.diagram_generator import DiagramGenerator
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
from research_analyser.storm_reporter import STORMReporter
from research_analyser.tts_engine import TTSEngine

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
        self.storm_reporter = STORMReporter(
            openai_api_key=self.config.openai_api_key,
            conv_model=self.config.storm.conv_model,
            outline_model=self.config.storm.outline_model,
            article_model=self.config.storm.article_model,
            max_conv_turn=self.config.storm.max_conv_turn,
            max_perspective=self.config.storm.max_perspective,
            search_top_k=self.config.storm.search_top_k,
            retrieve_top_k=self.config.storm.retrieve_top_k,
        )
        self.tts_engine = TTSEngine(
            model_name=self.config.tts.model,
            device=self.config.tts.device,
            speaker=self.config.tts.speaker,
        )

    async def analyse(
        self,
        source: str,
        source_type: Optional[str] = None,
        options: Optional[AnalysisOptions] = None,
        on_progress=None,
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

        def _progress(message: str) -> None:
            if on_progress is not None:
                try:
                    on_progress(message)
                except Exception:
                    pass

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
        _progress("⬇️  Fetching PDF…")
        pdf_path = await self.input_handler.resolve(paper_input)
        logger.info(f"Resolved to: {pdf_path}")
        _progress(f"✓  PDF ready — {pdf_path.name}")

        # 3. Extract content via MonkeyOCR
        _progress("🔍  Extracting content (OCR)…")
        content = await self.ocr_engine.extract(pdf_path)
        logger.info(
            f"Extracted: {len(content.equations)} equations, "
            f"{len(content.tables)} tables, {len(content.figures)} figures"
        )
        _progress(
            f"✓  Extracted {len(content.sections)} sections · "
            f"{len(content.equations)} equations · {len(content.figures)} figures"
        )

        # 4. Run analysis tasks in parallel
        task_names = (
            (["diagrams"] if options.generate_diagrams else [])
            + (["peer review"] if options.generate_review else [])
        )
        if task_names:
            _progress(f"🤖  Generating {' & '.join(task_names)}…")

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

        # 9. Generate STORM Wikipedia-style report (if requested)
        if options.generate_storm_report and self.config.storm.enabled:
            try:
                _progress("🌪️  Generating STORM Wikipedia report…")
                logger.info("Generating STORM report...")
                # STORMWikiRunner.run() makes blocking DSPy/litellm calls;
                # run in a thread to keep the event loop free (Principle II).
                report.storm_report = await asyncio.to_thread(
                    self.storm_reporter.generate, report
                )
                if report.storm_report:
                    storm_path = output_dir / "storm_report.md"
                    storm_path.write_text(report.storm_report, encoding="utf-8")
                    logger.info(f"STORM report saved to {storm_path}")
            except Exception as exc:
                logger.error(f"STORM report generation failed: {exc}")

        # 10. Generate audio narration (if requested)
        audio_path = None
        if options.generate_audio:
            try:
                _progress("🎙️  Generating audio narration (TTS)…")
                logger.info("Generating audio narration with Qwen3-TTS...")
                audio_path = await self.tts_engine.synthesize(report, output_dir)
                logger.info(f"Audio saved to: {audio_path}")
            except Exception as exc:
                logger.error(f"Audio generation failed: {exc}")

        logger.info(f"Analysis complete in {elapsed:.1f}s. Output: {output_dir}")

        return report

    def _extract_methodology_summary(self, content) -> str:
        """Extract methodology summary from sections.

        Strategy (in order):
        1. Broad title keyword match
        2. Content keyword match (look for "we propose", "algorithm", etc.)
        3. Positional fallback: sections 1–4 (intro is usually section 0)
        4. Full-text at offset 1000+ to skip the abstract area
        """
        abstract = (content.abstract or "").strip()

        def _distinct(text: str) -> bool:
            t = text.strip()
            return bool(t) and t[:200] != abstract[:200]

        METHOD_TITLE_KWS = [
            "method", "approach", "proposed", "framework", "technique",
            "model", "algorithm", "system", "design", "pipeline",
            "architecture", "contribution", "formulation", "solution",
            "overview", "our ",
        ]
        METHOD_CONTENT_KWS = [
            "we propose", "we present", "our method", "our approach",
            "the proposed", "algorithm", "architecture", "pipeline",
            "formulation", "framework",
        ]

        # 1. Title keyword match
        for section in content.sections:
            if any(kw in section.title.lower() for kw in METHOD_TITLE_KWS):
                text = section.content[:500].strip()
                if _distinct(text):
                    return text

        # 2. Content keyword match
        for section in content.sections:
            if any(kw in section.content.lower() for kw in METHOD_CONTENT_KWS):
                text = section.content[:500].strip()
                if _distinct(text):
                    return text

        # 3. Positional fallback: skip section 0 (usually intro), try 1–4
        if len(content.sections) > 1:
            for sec in content.sections[1:5]:
                text = sec.content[:500].strip()
                if _distinct(text):
                    return text

        # 4. Full-text at offset (beyond abstract area)
        if content.full_text and len(content.full_text) > 1000:
            return content.full_text[1000:1500].strip()

        return abstract[:500] if abstract else ""

    def _extract_results_summary(self, content) -> str:
        """Extract results summary from sections.

        Strategy (in order):
        1. Broad title keyword match
        2. Content keyword match in the latter half of sections
        3. Positional fallback: last few non-conclusion sections
        4. Full-text from the latter portion of the paper
        """
        abstract = (content.abstract or "").strip()

        def _distinct(text: str) -> bool:
            t = text.strip()
            return bool(t) and t[:200] != abstract[:200]

        RESULTS_TITLE_KWS = [
            "result", "experiment", "evaluation", "performance",
            "benchmark", "comparison", "analysis", "ablation",
            "finding", "quantitative", "accuracy", "discussion",
        ]
        RESULTS_CONTENT_KWS = [
            "table", "accuracy", "f1", "precision", "recall",
            "outperforms", "baseline", "state-of-the-art", "sota",
            "improvement", "score", "metric", "% ",
        ]

        # 1. Title keyword match
        for section in content.sections:
            if any(kw in section.title.lower() for kw in RESULTS_TITLE_KWS):
                text = section.content[:500].strip()
                if _distinct(text):
                    return text

        # 2. Content keyword match in latter half
        mid = max(0, len(content.sections) // 2)
        for section in content.sections[mid:]:
            if any(kw in section.content.lower() for kw in RESULTS_CONTENT_KWS):
                text = section.content[:500].strip()
                if _distinct(text):
                    return text

        # 3. Positional fallback: work backwards from second-to-last section
        if len(content.sections) >= 3:
            for sec in reversed(content.sections[:-1]):
                text = sec.content[:500].strip()
                if _distinct(text):
                    return text

        # 4. Full-text from latter portion
        if content.full_text and len(content.full_text) > 2000:
            return content.full_text[-1500:-1000].strip()
        if content.full_text and len(content.full_text) > 500:
            return content.full_text[-500:].strip()

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
