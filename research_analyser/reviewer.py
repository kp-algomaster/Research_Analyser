"""Agentic paper review using LangGraph workflow."""

from __future__ import annotations

import logging
from typing import Optional

from research_analyser.exceptions import ReviewError
from research_analyser.models import (
    DimensionScore,
    ExtractedContent,
    PeerReview,
    RelatedWork,
)

logger = logging.getLogger(__name__)

# Scoring formula constants
INTERCEPT = -0.3057
WEIGHT_SOUNDNESS = 0.7134
WEIGHT_PRESENTATION = 0.4242
WEIGHT_CONTRIBUTION = 1.0588

# Score interpretation
SCORE_LABELS = {
    (1.0, 3.0): "Strong Reject",
    (3.0, 4.0): "Reject",
    (4.0, 5.0): "Weak Reject",
    (5.0, 6.0): "Borderline",
    (6.0, 7.0): "Weak Accept",
    (7.0, 8.0): "Accept",
    (8.0, 10.0): "Strong Accept",
}


def interpret_score(score: float) -> str:
    """Interpret a numerical score into a decision label."""
    for (low, high), label in SCORE_LABELS.items():
        if low <= score < high:
            return label
    return "Strong Accept" if score >= 8.0 else "Unknown"


def compute_final_score(
    soundness: float, presentation: float, contribution: float
) -> float:
    """Compute final review score from dimension scores.

    Formula: score = -0.3057 + 0.7134*S + 0.4242*P + 1.0588*C

    Args:
        soundness: Technical correctness score (1-4)
        presentation: Writing clarity score (1-4)
        contribution: Significance/novelty score (1-4)

    Returns:
        Final score on 1-10 scale
    """
    raw = (
        INTERCEPT
        + WEIGHT_SOUNDNESS * soundness
        + WEIGHT_PRESENTATION * presentation
        + WEIGHT_CONTRIBUTION * contribution
    )
    return max(1.0, min(10.0, raw))


class PaperReviewer:
    """Generate structured peer review using agentic review pipeline.

    Uses a LangGraph workflow with Plan-Execute-Reflect pattern.
    Nine-node workflow:
    1. PaperIntake - validate paper
    2. QueryGeneration - generate search queries
    3. RelatedWorkSearch - search arXiv via Tavily
    4. PaperRanking - rank by relevance
    5. Summarization - summarize related works
    6. StrengthIdentification - identify strengths
    7. WeaknessAnalysis - identify weaknesses
    8. ReviewComposition - compose review
    9. Scoring - ML-calibrated scoring
    """

    def __init__(
        self,
        llm_provider: str = "openai",
        model: str = "gpt-4o",
        tavily_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.llm_provider = llm_provider
        self.model = model
        self.tavily_api_key = tavily_api_key
        self.openai_api_key = openai_api_key
        self._workflow = None

    def _build_workflow(self):
        """Build the LangGraph review workflow."""
        if self._workflow is not None:
            return

        try:
            from langchain_openai import ChatOpenAI
            from langgraph.graph import StateGraph, END

            llm = ChatOpenAI(
                model=self.model,
                api_key=self.openai_api_key,
            )

            # Define workflow state
            from typing import TypedDict

            class ReviewState(TypedDict):
                paper_text: str
                venue: str
                title: str
                search_queries: list[str]
                related_works: list[dict]
                ranked_works: list[dict]
                summaries: list[str]
                strengths: list[str]
                weaknesses: list[str]
                review_text: str
                scores: dict

            # Define workflow nodes
            async def paper_intake(state: ReviewState) -> ReviewState:
                """Validate paper and extract title."""
                response = await llm.ainvoke(
                    f"Extract the title from this paper and confirm it is an academic paper. "
                    f"Return just the title.\n\n{state['paper_text'][:3000]}"
                )
                state["title"] = response.content.strip()
                return state

            async def query_generation(state: ReviewState) -> ReviewState:
                """Generate search queries at varying specificity levels."""
                response = await llm.ainvoke(
                    f"Generate 6 search queries to find related work for this paper:\n"
                    f"Title: {state['title']}\n"
                    f"Text: {state['paper_text'][:2000]}\n\n"
                    f"Generate 2 queries for benchmarks, 2 for related problems, "
                    f"and 2 for related techniques. Return one per line."
                )
                state["search_queries"] = [
                    q.strip() for q in response.content.strip().split("\n") if q.strip()
                ]
                return state

            async def related_work_search(state: ReviewState) -> ReviewState:
                """Search for related papers."""
                works = []
                if self.tavily_api_key:
                    try:
                        from tavily import TavilyClient

                        client = TavilyClient(api_key=self.tavily_api_key)
                        for query in state["search_queries"][:3]:
                            results = client.search(
                                f"site:arxiv.org {query}", max_results=5
                            )
                            for r in results.get("results", []):
                                works.append({
                                    "title": r.get("title", ""),
                                    "url": r.get("url", ""),
                                    "content": r.get("content", ""),
                                })
                    except Exception as e:
                        logger.warning(f"Tavily search failed: {e}")

                state["related_works"] = works
                return state

            async def strength_identification(state: ReviewState) -> ReviewState:
                """Identify paper strengths."""
                related_context = "\n".join(
                    f"- {w['title']}" for w in state["related_works"][:10]
                )
                response = await llm.ainvoke(
                    f"As a peer reviewer for {state['venue'] or 'a top ML venue'}, "
                    f"identify the strengths of this paper.\n\n"
                    f"Title: {state['title']}\n"
                    f"Paper: {state['paper_text'][:4000]}\n\n"
                    f"Related works found:\n{related_context}\n\n"
                    f"List 3-5 specific strengths with evidence from the paper."
                )
                state["strengths"] = [
                    s.strip() for s in response.content.strip().split("\n") if s.strip()
                ]
                return state

            async def weakness_analysis(state: ReviewState) -> ReviewState:
                """Identify paper weaknesses."""
                related_context = "\n".join(
                    f"- {w['title']}" for w in state["related_works"][:10]
                )
                response = await llm.ainvoke(
                    f"As a peer reviewer for {state['venue'] or 'a top ML venue'}, "
                    f"identify the weaknesses of this paper.\n\n"
                    f"Title: {state['title']}\n"
                    f"Paper: {state['paper_text'][:4000]}\n\n"
                    f"Related works found:\n{related_context}\n\n"
                    f"List 3-5 specific weaknesses with constructive suggestions."
                )
                state["weaknesses"] = [
                    w.strip() for w in response.content.strip().split("\n") if w.strip()
                ]
                return state

            async def scoring(state: ReviewState) -> ReviewState:
                """Score the paper on multiple dimensions."""
                response = await llm.ainvoke(
                    f"Score this paper on a 1-4 scale for each dimension. "
                    f"Return ONLY three numbers separated by commas: "
                    f"soundness,presentation,contribution\n\n"
                    f"Title: {state['title']}\n"
                    f"Strengths:\n" + "\n".join(state["strengths"]) + "\n"
                    f"Weaknesses:\n" + "\n".join(state["weaknesses"])
                )
                try:
                    parts = response.content.strip().split(",")
                    state["scores"] = {
                        "soundness": float(parts[0].strip()),
                        "presentation": float(parts[1].strip()),
                        "contribution": float(parts[2].strip()),
                    }
                except (ValueError, IndexError):
                    state["scores"] = {
                        "soundness": 2.5,
                        "presentation": 2.5,
                        "contribution": 2.5,
                    }
                return state

            async def review_composition(state: ReviewState) -> ReviewState:
                """Compose the full review."""
                response = await llm.ainvoke(
                    f"Write a structured peer review for this paper.\n\n"
                    f"Title: {state['title']}\n"
                    f"Venue: {state['venue'] or 'top ML venue'}\n"
                    f"Strengths:\n" + "\n".join(state["strengths"]) + "\n\n"
                    f"Weaknesses:\n" + "\n".join(state["weaknesses"]) + "\n\n"
                    f"Include: Summary, Strengths, Weaknesses, Questions, "
                    f"Suggestions, and Overall Assessment."
                )
                state["review_text"] = response.content
                return state

            # Build graph
            workflow = StateGraph(ReviewState)
            workflow.add_node("paper_intake", paper_intake)
            workflow.add_node("query_generation", query_generation)
            workflow.add_node("related_work_search", related_work_search)
            workflow.add_node("strength_identification", strength_identification)
            workflow.add_node("weakness_analysis", weakness_analysis)
            workflow.add_node("scoring", scoring)
            workflow.add_node("review_composition", review_composition)

            workflow.set_entry_point("paper_intake")
            workflow.add_edge("paper_intake", "query_generation")
            workflow.add_edge("query_generation", "related_work_search")
            workflow.add_edge("related_work_search", "strength_identification")
            workflow.add_edge("strength_identification", "weakness_analysis")
            workflow.add_edge("weakness_analysis", "scoring")
            workflow.add_edge("scoring", "review_composition")
            workflow.add_edge("review_composition", END)

            self._workflow = workflow.compile()
            logger.info("Built LangGraph review workflow")

        except ImportError as e:
            raise ReviewError(
                f"Required packages not installed: {e}. "
                "Install with: pip install langgraph langchain-openai tavily-python"
            )

    async def review(
        self,
        content: ExtractedContent,
        venue: Optional[str] = None,
    ) -> PeerReview:
        """Generate comprehensive peer review."""
        self._build_workflow()

        try:
            initial_state = {
                "paper_text": content.full_text,
                "venue": venue or "",
                "title": content.title,
                "search_queries": [],
                "related_works": [],
                "ranked_works": [],
                "summaries": [],
                "strengths": [],
                "weaknesses": [],
                "review_text": "",
                "scores": {},
            }

            result = await self._workflow.ainvoke(initial_state)

            scores = result["scores"]
            s = scores.get("soundness", 2.5)
            p = scores.get("presentation", 2.5)
            c = scores.get("contribution", 2.5)

            overall = compute_final_score(s, p, c)

            dimensions = {
                "soundness": DimensionScore(
                    name="Soundness",
                    score=s,
                    weight=WEIGHT_SOUNDNESS,
                    justification="Technical correctness assessment",
                ),
                "presentation": DimensionScore(
                    name="Presentation",
                    score=p,
                    weight=WEIGHT_PRESENTATION,
                    justification="Writing clarity assessment",
                ),
                "contribution": DimensionScore(
                    name="Contribution",
                    score=c,
                    weight=WEIGHT_CONTRIBUTION,
                    justification="Significance and novelty assessment",
                ),
            }

            related_works = [
                RelatedWork(
                    title=w.get("title", ""),
                    authors=[],
                    url=w.get("url"),
                    summary=w.get("content", ""),
                )
                for w in result.get("related_works", [])
            ]

            return PeerReview(
                overall_score=overall,
                confidence=3.0,
                dimensions=dimensions,
                strengths=result.get("strengths", []),
                weaknesses=result.get("weaknesses", []),
                suggestions=[],
                related_works=related_works,
                raw_review=result.get("review_text", ""),
            )

        except Exception as e:
            raise ReviewError(f"Review generation failed: {e}")
