"""Tests for OCR engine equation extraction and section parsing."""

from research_analyser.ocr_engine import OCREngine


def test_extract_display_equations():
    engine = OCREngine()
    text = """
# Introduction

Some text here.

## Method

The loss function is defined as:

$$L = \\sum_{i=1}^{N} -y_i \\log(\\hat{y}_i)$$

And the gradient is:

$$\\nabla L = \\frac{\\partial L}{\\partial \\theta}$$
"""
    equations = engine.extract_equations(text)
    display_eqs = [eq for eq in equations if not eq.is_inline]

    assert len(display_eqs) == 2
    assert "\\sum" in display_eqs[0].latex
    assert "\\nabla" in display_eqs[1].latex


def test_extract_inline_equations():
    engine = OCREngine()
    text = "The variable $x \\in \\mathbb{R}^n$ represents the input and $f(x) = Wx + b$ is the output."

    equations = engine.extract_equations(text)
    inline_eqs = [eq for eq in equations if eq.is_inline]

    assert len(inline_eqs) >= 2


def test_parse_sections():
    engine = OCREngine()
    text = """# Title

Abstract content.

## Introduction

Intro text.

## Method

Method text.

### Sub-method

Sub-method text.

## Results

Results text.
"""
    sections = engine.parse_sections(text)

    assert len(sections) == 5
    assert sections[0].title == "Title"
    assert sections[0].level == 1
    assert sections[1].title == "Introduction"
    assert sections[3].title == "Sub-method"
    assert sections[3].level == 3


def test_extract_title():
    engine = OCREngine()
    from research_analyser.models import Section

    sections = [Section(title="My Paper Title", level=1, content="...")]
    title = engine._extract_title("# My Paper Title\n\nContent", sections)
    assert title == "My Paper Title"


def test_equation_label_extraction():
    engine = OCREngine()
    text = r"""
$$
\label{eq:loss}
L = \sum_{i=1}^{N} -y_i \log(\hat{y}_i)
$$
"""
    equations = engine.extract_equations(text)
    labeled = [eq for eq in equations if eq.label]
    assert len(labeled) >= 1
    assert labeled[0].label == "eq:loss"
