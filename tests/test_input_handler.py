"""Tests for input handler."""

import pytest

from research_analyser.input_handler import InputHandler
from research_analyser.models import SourceType


@pytest.fixture
def handler(tmp_path):
    return InputHandler(temp_dir=str(tmp_path))


def test_detect_arxiv_url(handler):
    assert handler.detect_source_type("https://arxiv.org/abs/2401.12345") == SourceType.ARXIV_ID


def test_detect_arxiv_pdf_url(handler):
    assert handler.detect_source_type("https://arxiv.org/pdf/2401.12345") == SourceType.ARXIV_ID


def test_detect_raw_arxiv_id(handler):
    assert handler.detect_source_type("2401.12345") == SourceType.ARXIV_ID


def test_detect_arxiv_with_version(handler):
    assert handler.detect_source_type("2401.12345v2") == SourceType.ARXIV_ID


def test_detect_doi(handler):
    assert handler.detect_source_type("10.1234/example.2024") == SourceType.DOI


def test_detect_url(handler):
    assert handler.detect_source_type("https://example.com/paper.pdf") == SourceType.PDF_URL


def test_detect_local_pdf(handler, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content")
    assert handler.detect_source_type(str(pdf)) == SourceType.PDF_FILE


def test_extract_arxiv_id(handler):
    assert handler._extract_arxiv_id("https://arxiv.org/abs/2401.12345") == "2401.12345"
    assert handler._extract_arxiv_id("https://arxiv.org/pdf/2401.12345v2") == "2401.12345v2"
    assert handler._extract_arxiv_id("2401.12345") == "2401.12345"
