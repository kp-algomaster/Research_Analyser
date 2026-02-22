"""Tests for research_analyser.storm_reporter (PaperContentRM + STORMReporter).

Principles verified: III (fail-safe), IV (models.py contracts).

Run with: pytest tests/test_storm_reporter.py -v
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.sample_content import make_extracted_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_dspy():
    """Return a minimal mock dspy module with Retrieve and Example."""
    mock = MagicMock()

    class FakeRetrieve:
        def __init__(self, k=3):
            self.k = k

        def __call__(self, *args, **kwargs):
            return self.forward(*args, **kwargs)

    mock.Retrieve = FakeRetrieve
    mock.Example = lambda **kw: types.SimpleNamespace(**kw)
    return mock


# ---------------------------------------------------------------------------
# _build_chunks
# ---------------------------------------------------------------------------

class TestBuildChunks:
    def test_includes_abstract_chunk(self):
        from research_analyser.storm_reporter import _build_chunks
        content = make_extracted_content()
        chunks = _build_chunks(content)
        urls = [c["url"] for c in chunks]
        assert any("abstract" in u for u in urls)

    def test_includes_section_chunks(self):
        from research_analyser.storm_reporter import _build_chunks
        content = make_extracted_content()
        chunks = _build_chunks(content)
        descriptions = [c["description"] for c in chunks]
        assert "Methodology" in descriptions
        assert "Introduction" in descriptions

    def test_includes_equation_chunk_when_descriptions_present(self):
        from research_analyser.storm_reporter import _build_chunks
        content = make_extracted_content()
        chunks = _build_chunks(content)
        descriptions = [c["description"] for c in chunks]
        assert any("Equation" in d for d in descriptions)

    def test_includes_reference_chunk(self):
        from research_analyser.storm_reporter import _build_chunks
        content = make_extracted_content()
        chunks = _build_chunks(content)
        descriptions = [c["description"] for c in chunks]
        assert any("Reference" in d for d in descriptions)

    def test_empty_sections_excluded(self):
        from research_analyser.storm_reporter import _build_chunks
        from research_analyser.models import Section
        content = make_extracted_content()
        content.sections.append(Section(title="Empty", level=2, content="   "))
        chunks = _build_chunks(content)
        descriptions = [c["description"] for c in chunks]
        assert "Empty" not in descriptions


# ---------------------------------------------------------------------------
# PaperContentRM — built via factory to avoid dspy import at test-collection time
# ---------------------------------------------------------------------------

class TestPaperContentRM:
    @pytest.fixture(autouse=True)
    def patch_dspy(self, monkeypatch):
        mock_dspy = _make_mock_dspy()
        monkeypatch.setitem(__import__("sys").modules, "dspy", mock_dspy)
        yield mock_dspy

    def _make_rm(self, k=5):
        from research_analyser.storm_reporter import _build_paper_rm_class
        cls = _build_paper_rm_class()
        return cls(make_extracted_content(), k=k)

    def test_forward_returns_at_most_k_results(self):
        rm = self._make_rm(k=2)
        results = rm.forward("methodology attention")
        assert len(results) <= 2

    def test_forward_deduplicates_across_queries(self):
        rm = self._make_rm(k=10)
        results = rm.forward(["methodology", "methodology"])
        urls = [r.url for r in results]
        assert len(urls) == len(set(urls)), "Duplicate URLs returned"

    def test_forward_no_match_still_returns_results(self):
        rm = self._make_rm(k=3)
        results = rm.forward("xyzzy nonsense token 99999")
        assert len(results) > 0

    def test_forward_excludes_specified_urls(self):
        rm = self._make_rm(k=10)
        # Collect all URLs first
        all_results = rm.forward("method")
        if not all_results:
            pytest.skip("No chunks available")
        excluded = {all_results[0].url}
        results_after = rm.forward("method", exclude_urls=list(excluded))
        returned_urls = {r.url for r in results_after}
        assert excluded.isdisjoint(returned_urls)

    def test_chunks_include_abstract(self):
        rm = self._make_rm()
        assert any("abstract" in c["url"] for c in rm.chunks)

    def test_chunks_include_equations(self):
        rm = self._make_rm()
        descriptions = [c["description"] for c in rm.chunks]
        assert any("Equation" in d for d in descriptions)

    def test_k_attribute_set(self):
        rm = self._make_rm(k=7)
        assert rm.k == 7


# ---------------------------------------------------------------------------
# STORMReporter
# ---------------------------------------------------------------------------

class TestSTORMReporter:
    def test_check_imports_raises_when_knowledge_storm_missing(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "knowledge_storm", None)  # type: ignore[assignment]
        from research_analyser.storm_reporter import STORMReporter
        reporter = STORMReporter(openai_api_key="test")
        with pytest.raises(ImportError, match="knowledge-storm"):
            reporter._check_imports()

    def test_generate_returns_article_string(self):
        """generate() returns the article text produced by _read_storm_output."""
        from research_analyser.storm_reporter import STORMReporter
        from research_analyser.models import (
            AnalysisOptions, AnalysisReport, PaperInput, PaperSummary,
            ReportMetadata, SourceType,
        )

        content = make_extracted_content()
        report = AnalysisReport(
            paper_input=PaperInput(
                source_type=SourceType.PDF_FILE,
                source_value="test.pdf",
                analysis_options=AnalysisOptions(),
            ),
            extracted_content=content,
            review=None,
            diagrams=[],
            summary=PaperSummary(
                one_sentence="Test",
                abstract_summary="",
                methodology_summary="",
                results_summary="",
                conclusions="",
            ),
            key_points=[],
            metadata=ReportMetadata(),
        )

        reporter = STORMReporter(openai_api_key="test-key")
        mock_runner = MagicMock()

        # STORMWikiRunner/RunnerArguments are local-imported inside generate(); patch the
        # source module so they resolve to our mocks at import time inside the function.
        import sys
        mock_ks = MagicMock()
        mock_ks.STORMWikiRunner.return_value = mock_runner
        mock_ks.STORMWikiRunnerArguments.return_value = MagicMock()

        with (
            patch("research_analyser.storm_reporter.STORMReporter._check_imports"),
            patch("research_analyser.storm_reporter._build_paper_rm_class", return_value=MagicMock()),
            patch("research_analyser.storm_reporter.STORMReporter._build_lm_configs", return_value=MagicMock()),
            patch("research_analyser.storm_reporter._read_storm_output", return_value="# Article\n\nContent."),
            patch.dict(sys.modules, {"knowledge_storm": mock_ks}),
        ):
            result = reporter.generate(report)

        assert result == "# Article\n\nContent."
        mock_runner.run.assert_called_once()
        mock_runner.post_run.assert_called_once()

    def test_generate_propagates_runner_exception(self):
        """generate() propagates exceptions so the fail-safe in analyser.py can catch them."""
        from research_analyser.storm_reporter import STORMReporter
        from research_analyser.models import (
            AnalysisOptions, AnalysisReport, PaperInput, PaperSummary,
            ReportMetadata, SourceType,
        )

        content = make_extracted_content()
        report = AnalysisReport(
            paper_input=PaperInput(
                source_type=SourceType.PDF_FILE,
                source_value="test.pdf",
                analysis_options=AnalysisOptions(),
            ),
            extracted_content=content,
            review=None,
            diagrams=[],
            summary=PaperSummary("", "", "", "", ""),
            key_points=[],
            metadata=ReportMetadata(),
        )

        reporter = STORMReporter(openai_api_key="test-key")
        mock_runner = MagicMock()
        mock_runner.run.side_effect = RuntimeError("LLM API failure")

        import sys
        mock_ks = MagicMock()
        mock_ks.STORMWikiRunner.return_value = mock_runner
        mock_ks.STORMWikiRunnerArguments.return_value = MagicMock()

        with (
            patch("research_analyser.storm_reporter.STORMReporter._check_imports"),
            patch("research_analyser.storm_reporter._build_paper_rm_class", return_value=MagicMock()),
            patch("research_analyser.storm_reporter.STORMReporter._build_lm_configs", return_value=MagicMock()),
            patch.dict(sys.modules, {"knowledge_storm": mock_ks}),
        ):
            with pytest.raises(RuntimeError, match="LLM API failure"):
                reporter.generate(report)


# ---------------------------------------------------------------------------
# _read_storm_output
# ---------------------------------------------------------------------------

class TestReadStormOutput:
    def test_prefers_polished_article(self, tmp_path):
        from research_analyser.storm_reporter import _read_storm_output
        nested = tmp_path / "my_topic"
        nested.mkdir()
        (nested / "storm_gen_article.txt").write_text("raw article")
        (nested / "storm_gen_article_polished.txt").write_text("polished article")
        assert _read_storm_output(tmp_path) == "polished article"

    def test_falls_back_to_raw_article(self, tmp_path):
        from research_analyser.storm_reporter import _read_storm_output
        nested = tmp_path / "my_topic"
        nested.mkdir()
        (nested / "storm_gen_article.txt").write_text("raw article")
        assert _read_storm_output(tmp_path) == "raw article"

    def test_falls_back_to_any_txt(self, tmp_path):
        from research_analyser.storm_reporter import _read_storm_output
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        (deep / "outline.txt").write_text("outline text")
        assert _read_storm_output(tmp_path) == "outline text"

    def test_returns_empty_string_when_no_files(self, tmp_path):
        from research_analyser.storm_reporter import _read_storm_output
        assert _read_storm_output(tmp_path) == ""

    def test_skips_empty_files(self, tmp_path):
        from research_analyser.storm_reporter import _read_storm_output
        nested = tmp_path / "topic"
        nested.mkdir()
        (nested / "storm_gen_article_polished.txt").write_text("")
        (nested / "storm_gen_article.txt").write_text("fallback")
        assert _read_storm_output(tmp_path) == "fallback"


# ---------------------------------------------------------------------------
# StormConfig validators
# ---------------------------------------------------------------------------

class TestStormConfig:
    def test_defaults_are_valid(self):
        from research_analyser.config import StormConfig
        cfg = StormConfig()
        assert cfg.max_conv_turn >= 1
        assert cfg.max_perspective >= 1
        assert cfg.search_top_k >= 1
        assert cfg.retrieve_top_k >= 1
        assert cfg.enabled is False

    def test_invalid_max_conv_turn_raises(self):
        from pydantic import ValidationError
        from research_analyser.config import StormConfig
        with pytest.raises(ValidationError):
            StormConfig(max_conv_turn=0)

    def test_invalid_max_perspective_raises(self):
        from pydantic import ValidationError
        from research_analyser.config import StormConfig
        with pytest.raises(ValidationError):
            StormConfig(max_perspective=0)

    def test_storm_config_loaded_from_yaml(self, tmp_path):
        """StormConfig fields round-trip through Config.load() from a YAML file."""
        import yaml
        from research_analyser.config import Config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.dump(
                {
                    "storm": {
                        "enabled": True,
                        "conv_model": "gpt-3.5-turbo",
                        "max_conv_turn": 5,
                        "max_perspective": 2,
                    }
                }
            )
        )
        cfg = Config.load(str(cfg_file))
        assert cfg.storm.enabled is True
        assert cfg.storm.conv_model == "gpt-3.5-turbo"
        assert cfg.storm.max_conv_turn == 5
        assert cfg.storm.max_perspective == 2

    def test_storm_config_disabled_skips_generation(self, tmp_path):
        """When storm.enabled=False the STORMReporter.generate() is never called."""
        import asyncio
        import yaml
        from unittest.mock import AsyncMock, patch as up
        from research_analyser.config import Config
        from research_analyser.analyser import ResearchAnalyser
        from research_analyser.models import AnalysisOptions

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.dump(
                {
                    "app": {"output_dir": str(tmp_path / "output"), "temp_dir": str(tmp_path / "tmp")},
                    "storm": {"enabled": False},
                }
            )
        )
        cfg = Config.load(str(cfg_file))
        analyser = ResearchAnalyser(config=cfg)

        # Patch every pipeline stage so only the STORM guard is tested.
        mock_report = MagicMock()
        mock_report.storm_report = None
        mock_report.metadata.analysed_at.isoformat.return_value = "2026-02-22"

        with (
            up.object(analyser.input_handler, "detect_source_type", return_value=MagicMock()),
            up.object(analyser.input_handler, "resolve", new=AsyncMock(return_value=tmp_path / "p.pdf")),
            up.object(analyser.ocr_engine, "extract", new=AsyncMock(return_value=MagicMock(
                title="T", authors=[], abstract="", sections=[], equations=[], tables=[],
                figures=[], references=[], full_text="", reading_order=[], metadata={},
            ))),
            up.object(analyser.diagram_generator, "generate", new=AsyncMock(return_value=[])),
            up.object(analyser.reviewer, "review", new=AsyncMock(return_value=None)),
            up.object(analyser.report_generator, "save_all"),
            up.object(analyser.storm_reporter, "generate") as mock_gen,
        ):
            options = AnalysisOptions(
                generate_diagrams=False,
                generate_review=False,
                generate_storm_report=True,  # requested, but storm.enabled=False
                generate_audio=False,
            )
            asyncio.run(analyser.analyse("fake.pdf", options=options))

        mock_gen.assert_not_called()
