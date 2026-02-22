"""Streamlit Web UI for Research Analyser."""

import asyncio
import json
import logging
import os
from pathlib import Path

import streamlit as st

from research_analyser.analyser import ResearchAnalyser
from research_analyser.comparison import (
    ReviewSnapshot,
    build_comparison_markdown,
    parse_external_review,
    parse_local_review,
)
from research_analyser.config import Config
from research_analyser.models import AnalysisOptions
from research_analyser.reviewer import interpret_score

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Research Analyser",
    page_icon="🔬",
    layout="wide",
)

st.title("Research Analyser")
st.markdown("AI-powered research paper analysis with OCR, diagram generation, and peer review.")


# Sidebar configuration
st.sidebar.header("Configuration")

# --- API Keys ---
st.sidebar.subheader("API Keys")
google_api_key = st.sidebar.text_input(
    "Google API Key (PaperBanana diagrams)",
    value=os.environ.get("GOOGLE_API_KEY", ""),
    type="password",
    help="Required for PaperBanana diagram generation with Gemini models",
)
openai_api_key = st.sidebar.text_input(
    "OpenAI API Key (Peer Review)",
    value=os.environ.get("OPENAI_API_KEY", ""),
    type="password",
    help="Required for agentic peer review with GPT-4o",
)
tavily_api_key = st.sidebar.text_input(
    "Tavily API Key (Related Work Search)",
    value=os.environ.get("TAVILY_API_KEY", ""),
    type="password",
    help="Optional: enables related-work search during review",
)

st.sidebar.divider()

# --- Analysis Options ---
st.sidebar.subheader("Analysis Options")
generate_diagrams = st.sidebar.checkbox("Generate Diagrams", value=True)
generate_review = st.sidebar.checkbox("Generate Peer Review", value=True)
diagram_types = st.sidebar.multiselect(
    "Diagram Types",
    ["methodology", "architecture", "results"],
    default=["methodology"],
)
diagram_provider = st.sidebar.selectbox(
    "Diagram Provider",
    ["google", "openai", "openrouter"],
    index=0,
    help="PaperBanana VLM provider for diagram generation",
)
venue = st.sidebar.text_input("Target Venue (optional)", placeholder="e.g., ICLR 2026")
output_dir = st.sidebar.text_input("Output Directory", value="./output")

# Main input area
st.header("Input")
input_tab1, input_tab2 = st.tabs(["Upload PDF", "Paper URL / arXiv ID"])

source = None
uploaded_file = None

with input_tab1:
    uploaded_file = st.file_uploader("Upload a research paper (PDF)", type=["pdf"])
    if uploaded_file:
        st.success(f"Uploaded: {uploaded_file.name}")

with input_tab2:
    url_input = st.text_input(
        "Enter paper URL, arXiv ID, or DOI",
        placeholder="https://arxiv.org/abs/2401.12345",
    )
    if url_input:
        source = url_input

# Run analysis
if st.button("Analyse Paper", type="primary", use_container_width=True):
    if not source and not uploaded_file:
        st.error("Please upload a PDF or enter a paper URL.")
    else:
        # Set API keys in environment so PaperBanana and LangChain pick them up
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        if tavily_api_key:
            os.environ["TAVILY_API_KEY"] = tavily_api_key

        config = Config.load()
        config.app.output_dir = output_dir
        config.diagrams.provider = diagram_provider

        # Pass API keys through config
        if google_api_key:
            config.google_api_key = google_api_key
        if openai_api_key:
            config.openai_api_key = openai_api_key
        if tavily_api_key:
            config.tavily_api_key = tavily_api_key

        options = AnalysisOptions(
            generate_diagrams=generate_diagrams,
            generate_review=generate_review,
            diagram_types=diagram_types,
        )

        analyser = ResearchAnalyser(config=config)

        # Handle file upload
        if uploaded_file:
            tmp_dir = Path(config.app.temp_dir) / "uploads"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            file_path = tmp_dir / uploaded_file.name
            file_path.write_bytes(uploaded_file.read())
            source = str(file_path)

        with st.spinner("Analysing paper... This may take a few minutes."):
            try:
                report = asyncio.run(analyser.analyse(source, options=options))

                # Display results
                st.header("Analysis Results")

                # Paper info
                st.subheader(report.extracted_content.title)
                if report.extracted_content.authors:
                    st.write(f"**Authors:** {', '.join(report.extracted_content.authors)}")

                # Summary
                if report.summary:
                    st.subheader("Summary")
                    st.write(report.summary.one_sentence)
                    with st.expander("Full Summary"):
                        st.write(report.summary.abstract_summary)
                        st.write("**Methodology:**", report.summary.methodology_summary)
                        st.write("**Results:**", report.summary.results_summary)

                # Key Findings
                if report.key_points:
                    st.subheader("Key Findings")
                    for kp in report.key_points:
                        with st.expander(f"{'🔴' if kp.importance == 'high' else '🟡'} {kp.point}"):
                            st.write(f"**Evidence:** {kp.evidence}")
                            st.write(f"**Section:** {kp.section}")

                # Statistics
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Equations", len(report.extracted_content.equations))
                col2.metric("Tables", len(report.extracted_content.tables))
                col3.metric("Figures", len(report.extracted_content.figures))
                col4.metric("References", len(report.extracted_content.references))

                # Equations
                display_eqs = [
                    eq for eq in report.extracted_content.equations if not eq.is_inline
                ]
                if display_eqs:
                    st.subheader("Key Equations")
                    for eq in display_eqs[:10]:
                        label = eq.label or eq.id
                        with st.expander(f"Equation: {label}"):
                            st.latex(eq.latex)
                            st.write(f"**Section:** {eq.section}")
                            if eq.description:
                                st.write(f"**Description:** {eq.description}")

                # Diagrams
                if report.diagrams:
                    st.subheader("Generated Diagrams")
                    for diagram in report.diagrams:
                        st.write(f"**{diagram.diagram_type.title()}**")
                        if Path(diagram.image_path).exists():
                            st.image(diagram.image_path, caption=diagram.caption)
                        else:
                            st.info(f"Diagram saved to: {diagram.image_path}")

                # Peer Review
                if report.review:
                    st.subheader("Peer Review")
                    score = report.review.overall_score
                    decision = interpret_score(score)

                    col_score, col_decision, col_conf = st.columns(3)
                    col_score.metric("Overall Score", f"{score:.1f}/10")
                    col_decision.metric("Decision", decision)
                    col_conf.metric("Confidence", f"{report.review.confidence:.0f}/5")

                    # Dimension scores
                    st.write("**Dimensional Scores:**")
                    for name, dim in report.review.dimensions.items():
                        st.progress(dim.score / 4.0, text=f"{dim.name}: {dim.score:.1f}/4")

                    col_s, col_w = st.columns(2)
                    with col_s:
                        st.write("**Strengths:**")
                        for s in report.review.strengths:
                            st.write(f"+ {s}")
                    with col_w:
                        st.write("**Weaknesses:**")
                        for w in report.review.weaknesses:
                            st.write(f"- {w}")

                # Download outputs
                st.subheader("Download Reports")
                report_md = report.to_markdown()
                st.download_button(
                    "Download Full Report (Markdown)",
                    report_md,
                    file_name="analysis_report.md",
                    mime="text/markdown",
                )

                st.success(f"All outputs saved to: {output_dir}")

                # Store report in session state for comparison
                st.session_state["last_report"] = report

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                st.exception(e)


# ------- PaperReview.ai Comparison Section -------
st.divider()
st.header("PaperReview.ai Comparison")
st.markdown(
    "Upload a review JSON from [PaperReview.ai](https://paperreview.ai) to compare "
    "against the local agentic review."
)
st.markdown(
    "**Expected JSON format:** "
    '`{"overall_score": 6.9, "soundness": 3.1, "presentation": 3.0, '
    '"contribution": 3.2, "confidence": 3.5}`'
)

ext_file = st.file_uploader(
    "Upload external review (JSON)",
    type=["json"],
    key="external_review",
)

if ext_file is not None:
    try:
        raw_bytes = ext_file.getvalue()
        ext_data = json.loads(raw_bytes.decode("utf-8"))

        external = ReviewSnapshot(
            source=f"paperreview.ai:{ext_file.name}",
            overall_score=ext_data.get("overall_score") or ext_data.get("review_score") or ext_data.get("overall"),
            soundness=ext_data.get("soundness"),
            presentation=ext_data.get("presentation"),
            contribution=ext_data.get("contribution"),
            confidence=ext_data.get("confidence"),
        )

        # Show external review scores immediately
        st.subheader("External Review (PaperReview.ai)")
        ext_cols = st.columns(5)
        ext_cols[0].metric("Overall", f"{external.overall_score:.1f}/10" if external.overall_score else "n/a")
        ext_cols[1].metric("Soundness", f"{external.soundness:.1f}/4" if external.soundness else "n/a")
        ext_cols[2].metric("Presentation", f"{external.presentation:.1f}/4" if external.presentation else "n/a")
        ext_cols[3].metric("Contribution", f"{external.contribution:.1f}/4" if external.contribution else "n/a")
        ext_cols[4].metric("Confidence", f"{external.confidence:.1f}/5" if external.confidence else "n/a")

        if external.overall_score is not None:
            st.info(f"**PaperReview.ai Decision:** {interpret_score(external.overall_score)}")

        # Build local snapshot from session state or output dir
        local = ReviewSnapshot(source="local", overall_score=None)
        last_report = st.session_state.get("last_report")
        if last_report and last_report.review:
            review = last_report.review
            dims = review.dimensions or {}
            local = ReviewSnapshot(
                source="local",
                overall_score=review.overall_score,
                soundness=dims.get("soundness").score if dims.get("soundness") else None,
                presentation=dims.get("presentation").score if dims.get("presentation") else None,
                contribution=dims.get("contribution").score if dims.get("contribution") else None,
                confidence=review.confidence,
            )
        else:
            local = parse_local_review(Path(output_dir))

        # Comparison table
        st.subheader("Score Comparison")
        comparison_md = build_comparison_markdown(local, external)
        st.markdown(comparison_md)

        st.download_button(
            "Download Comparison (Markdown)",
            comparison_md,
            file_name="review_comparison.md",
            mime="text/markdown",
        )
    except json.JSONDecodeError:
        st.error("Invalid JSON file. Please upload a valid review JSON.")
    except Exception as e:
        st.error(f"Comparison failed: {e}")
        st.exception(e)
