"""Shared fixtures for Research Analyser tests."""

from __future__ import annotations

from research_analyser.models import (
    Equation,
    ExtractedContent,
    Figure,
    Reference,
    Section,
    Table,
)


def make_extracted_content(
    title: str = "Attention Is All You Need",
    abstract: str = (
        "We propose a new network architecture, the Transformer, based solely on attention "
        "mechanisms, dispensing with recurrence and convolutions entirely."
    ),
) -> ExtractedContent:
    """Return a minimal but realistic ExtractedContent for use in unit tests."""
    sections = [
        Section(
            title="Introduction",
            level=1,
            content=(
                "Recurrent neural networks have been the dominant approach to sequence modelling. "
                "However, they inherently sequential nature precludes parallelisation within training "
                "examples."
            ),
        ),
        Section(
            title="Methodology",
            level=1,
            content=(
                "The Transformer follows an encoder-decoder structure. Both the encoder and decoder "
                "are composed of a stack of N identical layers. Each layer has two sub-layers: a "
                "multi-head self-attention mechanism and a position-wise feed-forward network."
            ),
        ),
        Section(
            title="Results",
            level=1,
            content=(
                "On the WMT 2014 English-to-German translation task, the big Transformer model "
                "outperforms the best previously reported models including ensembles by more than "
                "2.0 BLEU, establishing a new state-of-the-art BLEU score of 28.4."
            ),
        ),
    ]

    equations = [
        Equation(
            id="eq1",
            latex=r"\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^T}{\sqrt{d_k}}\right)V",
            context="Scaled dot-product attention formula",
            section="Methodology",
            is_inline=False,
            label="eq:attention",
            description="Scaled dot-product attention: queries, keys, and values matrix computation",
        ),
        Equation(
            id="eq2",
            latex=r"\text{PE}_{(pos,2i)} = \sin(pos / 10000^{2i/d_{\text{model}}})",
            context="Positional encoding",
            section="Methodology",
            is_inline=False,
            label="eq:pe",
            description="Sinusoidal positional encoding for even dimensions",
        ),
    ]

    references = [
        Reference(
            id="ref1",
            text="Bahdanau, D., Cho, K., & Bengio, Y. (2015). Neural machine translation by jointly learning to align and translate.",
            title="Neural machine translation by jointly learning to align and translate",
            authors=["Bahdanau, D.", "Cho, K.", "Bengio, Y."],
            year=2015,
        ),
        Reference(
            id="ref2",
            text="LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436-444.",
            title="Deep learning",
            authors=["LeCun, Y.", "Bengio, Y.", "Hinton, G."],
            year=2015,
            venue="Nature",
        ),
    ]

    return ExtractedContent(
        full_text="\n\n".join(
            [abstract] + [f"## {s.title}\n\n{s.content}" for s in sections]
        ),
        title=title,
        authors=["Vaswani, A.", "Shazeer, N.", "Parmar, N."],
        abstract=abstract,
        sections=sections,
        equations=equations,
        tables=[
            Table(
                id="tab1",
                content="| Model | BLEU |\n|---|---|\n| Transformer | 28.4 |",
                caption="WMT 2014 EN-DE results",
                section="Results",
            )
        ],
        figures=[
            Figure(id="fig1", caption="Transformer architecture", section="Methodology")
        ],
        references=references,
    )
