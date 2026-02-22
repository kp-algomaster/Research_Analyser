"""STORM-powered Wikipedia-style report generation for paper analysis.

Uses Stanford OVAL's knowledge-storm library to generate a comprehensive,
cited article about the paper's topic from the extracted content.

Requires: pip install knowledge-storm
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from research_analyser.models import AnalysisReport, ExtractedContent

logger = logging.getLogger(__name__)


def _build_paper_rm_class():
    """Return PaperContentRM class built with dspy.Retrieve as base.

    Deferred so that the module can be imported without knowledge-storm
    installed; a clear ImportError is raised only when actually used.
    """
    try:
        import dspy
    except ImportError as e:
        raise ImportError(
            "dspy-ai is required for STORM integration. "
            "Install it via: pip install knowledge-storm"
        ) from e

    class PaperContentRM(dspy.Retrieve):
        """STORM retrieval module backed by the paper's extracted content.

        Serves paper sections, equations, and references as ranked search
        results without requiring an external search API or vector database.
        """

        def __init__(self, content: ExtractedContent, k: int = 5):
            super().__init__(k=k)
            self.chunks = _build_chunks(content)

        def forward(self, query_or_queries, exclude_urls=None):
            """Return top-k paper chunks most relevant to the query."""
            queries = (
                [query_or_queries]
                if isinstance(query_or_queries, str)
                else list(query_or_queries)
            )
            exclude_urls = set(exclude_urls or [])
            results = []
            seen: set[str] = set(exclude_urls)

            for query in queries:
                q = query.lower()
                scored = []
                for chunk in self.chunks:
                    if chunk["url"] in seen:
                        continue
                    score = sum(
                        1
                        for word in q.split()
                        if word in chunk["description"].lower()
                        or any(word in s.lower() for s in chunk["snippets"])
                    )
                    scored.append((score, chunk))
                scored.sort(key=lambda x: x[0], reverse=True)
                for _, chunk in scored[: self.k]:
                    if chunk["url"] not in seen:
                        seen.add(chunk["url"])
                        results.append(
                            dspy.Example(
                                url=chunk["url"],
                                description=chunk["description"],
                                snippets=chunk["snippets"],
                            )
                        )

            return results

    return PaperContentRM


def _build_chunks(content: ExtractedContent) -> list[dict]:
    """Convert extracted paper content into STORM-compatible retrieval chunks."""
    chunks: list[dict] = []
    base = f"paper://{content.title.replace(' ', '-').lower()}"

    if content.abstract:
        chunks.append(
            {
                "url": f"{base}/abstract",
                "description": "Abstract",
                "snippets": [content.abstract],
            }
        )

    for section in content.sections:
        body = section.content.strip()
        if body:
            chunks.append(
                {
                    "url": f"{base}/{section.title.lower().replace(' ', '-')}",
                    "description": section.title,
                    "snippets": [body[:2000]],
                }
            )

    # Key equations with natural-language descriptions
    eq_lines = [
        f"{eq.label or eq.id}: {eq.description}"
        for eq in content.equations
        if eq.description and not eq.is_inline
    ]
    if eq_lines:
        chunks.append(
            {
                "url": f"{base}/equations",
                "description": "Key Equations and Mathematical Formulations",
                "snippets": ["\n".join(eq_lines[:15])],
            }
        )

    # References summary
    ref_texts = [r.text for r in content.references[:30]]
    if ref_texts:
        chunks.append(
            {
                "url": f"{base}/references",
                "description": "Bibliography and References",
                "snippets": ref_texts[:10],
            }
        )

    return chunks


class STORMReporter:
    """Generate Wikipedia-style STORM reports from an AnalysisReport.

    Uses the paper's extracted content as the retrieval corpus so no
    external search API key is required.  The topic fed to STORM is the
    paper title; STORM produces a structured, multi-perspective article.
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        conv_model: str = "gpt-4o-mini",
        outline_model: str = "gpt-4o",
        article_model: str = "gpt-4o",
        max_conv_turn: int = 3,
        max_perspective: int = 3,
        search_top_k: int = 5,
        retrieve_top_k: int = 5,
    ):
        self.openai_api_key = openai_api_key
        self.conv_model = conv_model
        self.outline_model = outline_model
        self.article_model = article_model
        self.max_conv_turn = max_conv_turn
        self.max_perspective = max_perspective
        self.search_top_k = search_top_k
        self.retrieve_top_k = retrieve_top_k

    def _check_imports(self) -> None:
        try:
            import knowledge_storm  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "knowledge-storm is required for STORM report generation. "
                "Install it via: pip install knowledge-storm"
            ) from e

    def _build_lm_configs(self):
        from knowledge_storm import STORMWikiLMConfigs
        from knowledge_storm.lm import LitellmModel

        kwargs: dict = {
            "api_key": self.openai_api_key,
            "temperature": 1.0,
            "top_p": 0.9,
        }
        conv_lm = LitellmModel(model=self.conv_model, max_tokens=500, **kwargs)
        outline_lm = LitellmModel(model=self.outline_model, max_tokens=4000, **kwargs)
        article_lm = LitellmModel(model=self.article_model, max_tokens=4000, **kwargs)

        lm_configs = STORMWikiLMConfigs()
        lm_configs.set_conv_simulator_lm(conv_lm)
        lm_configs.set_question_asker_lm(conv_lm)
        lm_configs.set_outline_gen_lm(outline_lm)
        lm_configs.set_article_gen_lm(article_lm)
        lm_configs.set_article_polish_lm(article_lm)
        return lm_configs

    def generate(self, report: AnalysisReport) -> str:
        """Run the STORM pipeline and return the generated article text.

        Args:
            report: The completed AnalysisReport from the analysis pipeline.

        Returns:
            A full Wikipedia-style article about the paper's topic with
            citations drawn from the paper's own content.
        """
        self._check_imports()
        from knowledge_storm import STORMWikiRunner, STORMWikiRunnerArguments

        content = report.extracted_content
        topic = content.title

        PaperContentRM = _build_paper_rm_class()

        with tempfile.TemporaryDirectory() as tmpdir:
            engine_args = STORMWikiRunnerArguments(
                output_dir=tmpdir,
                max_conv_turn=self.max_conv_turn,
                max_perspective=self.max_perspective,
                search_top_k=self.search_top_k,
                retrieve_top_k=self.retrieve_top_k,
            )

            lm_configs = self._build_lm_configs()
            rm = PaperContentRM(content, k=self.retrieve_top_k)

            runner = STORMWikiRunner(engine_args, lm_configs, rm)
            runner.run(
                topic=topic,
                do_research=True,
                do_generate_outline=True,
                do_generate_article=True,
                do_polish_article=True,
            )
            runner.post_run()

            article_text = _read_storm_output(Path(tmpdir))

        if not article_text:
            logger.warning("STORM did not produce an article for topic: %s", topic)

        return article_text


def _read_storm_output(base: Path) -> str:
    """Find and return the best available STORM output file.

    STORM sanitises topic names in various ways so we search broadly
    rather than constructing the path from the topic string.
    """
    for filename in ("storm_gen_article_polished.txt", "storm_gen_article.txt"):
        for candidate in base.rglob(filename):
            text = candidate.read_text(encoding="utf-8")
            if text.strip():
                return text

    # Last resort: any non-empty .txt under the output tree
    for candidate in sorted(base.rglob("*.txt")):
        text = candidate.read_text(encoding="utf-8")
        if text.strip():
            return text

    return ""
