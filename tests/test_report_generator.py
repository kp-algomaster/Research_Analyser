"""Tests for research_analyser.report_generator — storm_report.md persistence (T020).

Principles verified: I (pipeline outputs via save_all), IV (models.py contracts).

Run with: pytest tests/test_report_generator.py -v
"""

from __future__ import annotations

from datetime import datetime

from research_analyser.models import (
    AnalysisOptions,
    AnalysisReport,
    PaperInput,
    PaperSummary,
    ReportMetadata,
    SourceType,
)
from research_analyser.report_generator import ReportGenerator
from tests.fixtures.sample_content import make_extracted_content


def _make_report(storm_report=None) -> AnalysisReport:
    return AnalysisReport(
        paper_input=PaperInput(
            source_type=SourceType.PDF_FILE,
            source_value="test.pdf",
            analysis_options=AnalysisOptions(),
        ),
        extracted_content=make_extracted_content(),
        review=None,
        diagrams=[],
        summary=PaperSummary(
            one_sentence="Test paper.",
            abstract_summary="Abstract.",
            methodology_summary="Method.",
            results_summary="Results.",
            conclusions="Conclusion.",
        ),
        key_points=[],
        metadata=ReportMetadata(analysed_at=datetime(2026, 2, 22)),
        storm_report=storm_report,
    )


class TestSaveAllStormReport:
    def test_writes_storm_report_when_set(self, tmp_path):
        report = _make_report(storm_report="# STORM Article\n\nGenerated content.")
        ReportGenerator().save_all(report, tmp_path)
        storm_file = tmp_path / "storm_report.md"
        assert storm_file.exists(), "storm_report.md should be created"
        assert storm_file.read_text(encoding="utf-8") == "# STORM Article\n\nGenerated content."

    def test_does_not_write_storm_report_when_none(self, tmp_path):
        report = _make_report(storm_report=None)
        ReportGenerator().save_all(report, tmp_path)
        assert not (tmp_path / "storm_report.md").exists()

    def test_does_not_write_storm_report_when_empty_string(self, tmp_path):
        """Empty string is falsy — save_all should not create the file."""
        report = _make_report(storm_report="")
        ReportGenerator().save_all(report, tmp_path)
        assert not (tmp_path / "storm_report.md").exists()

    def test_standard_outputs_still_written(self, tmp_path):
        """save_all produces all standard files regardless of storm_report presence."""
        report = _make_report(storm_report="# Article")
        ReportGenerator().save_all(report, tmp_path)
        for name in ("report.md", "key_points.md", "spec_output.md", "report.html", "metadata.json"):
            assert (tmp_path / name).exists(), f"{name} missing"

    def test_storm_report_content_is_exact(self, tmp_path):
        content = "# Section 1\n\nParagraph.\n\n## Section 2\n\nMore text."
        report = _make_report(storm_report=content)
        ReportGenerator().save_all(report, tmp_path)
        written = (tmp_path / "storm_report.md").read_text(encoding="utf-8")
        assert written == content
