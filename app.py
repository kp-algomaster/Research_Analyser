"""Streamlit Web UI for Research Analyser."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import streamlit as st

# Lightweight imports only — heavy ML libs are deferred to handler scope
# so the initial page render is fast (no 30-60 s skeleton freeze).
from research_analyser.config import Config
from research_analyser.models import AnalysisOptions

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Research Analyser",
    page_icon="🔬",
    layout="wide",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .badge-green  { background: #1a4a1a; color: #4ade80; border: 1px solid #166534; }
    .badge-gray   { background: #2a2a2a; color: #9ca3af; border: 1px solid #374151; }
    .dot-green    { color: #4ade80; }
    .dot-red      { color: #f87171; }
    .svc-url      { font-size: 0.78rem; color: #6b7280; margin-top: -8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Server Management helpers ─────────────────────────────────────────────────

_SERVICES: dict[str, dict] = {
    "Analysis API": {
        "url": "http://127.0.0.1:8000",
        "health": "http://127.0.0.1:8000/api/v1/health",
        "cmd": [
            sys.executable,
            "-m",
            "uvicorn",
            "research_analyser.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        "devices": ["auto", "mps", "cpu"],
        "managed": True,
    },
    "OCR Engine": {
        "url": "In-process",
        "health": None,
        "cmd": None,
        "devices": ["auto", "mps", "cpu"],
        "managed": False,
    },
    "Review Engine": {
        "url": "In-process",
        "health": None,
        "cmd": None,
        "devices": ["auto", "cpu"],
        "managed": False,
    },
}


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as r:
            return r.status < 400
    except Exception:
        return False


def _active_device_label(device: str) -> str:
    """Return the hardware backend label for a given device setting."""
    if device in ("auto", "mps"):
        try:
            import torch

            if torch.backends.mps.is_available():
                return "MLX (METAL)"
            if torch.cuda.is_available():
                return "CUDA"
        except ImportError:
            pass
    return "CPU"


def _is_connected(name: str) -> bool:
    svc = _SERVICES[name]
    if svc["health"]:
        return _http_ok(svc["health"])
    if name == "OCR Engine":
        return True  # always available in-process
    if name == "Review Engine":
        return True
    return False


def _proc_running(name: str) -> bool:
    proc = st.session_state.get(f"proc_{name}")
    return proc is not None and proc.poll() is None


def _start_service(name: str) -> None:
    cmd = _SERVICES[name]["cmd"]
    if cmd is None:
        return
    device = st.session_state.get(f"device_{name}", "auto")
    env = {**os.environ}
    if device != "auto":
        env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
        env["DEVICE"] = device
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    st.session_state[f"proc_{name}"] = proc


def _stop_service(name: str) -> None:
    proc = st.session_state.get(f"proc_{name}")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    st.session_state.pop(f"proc_{name}", None)


def show_server_management() -> None:
    """Render the Server Management page."""

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Server Management")

        for name, svc in _SERVICES.items():
            connected = _is_connected(name)
            device = st.session_state.get(f"device_{name}", "auto")
            dot_cls = "dot-green" if connected else "dot-red"
            dot_label = "Connected" if connected else "Disconnected"

            with st.container(border=True):
                # Header row: name + connection status
                hdr_l, hdr_r = st.columns([4, 2])
                hdr_l.markdown(f"**{name}**")
                hdr_r.markdown(
                    f'<span class="{dot_cls}">●</span> {dot_label}',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<p class="svc-url">{svc["url"]}</p>', unsafe_allow_html=True
                )

                # Controls row
                b_restart, b_stop, _, dev_col, act_col = st.columns(
                    [1.1, 1, 0.3, 1.8, 2]
                )

                if b_restart.button("↺ Restart", key=f"restart_{name}", use_container_width=True):
                    if svc["managed"]:
                        _stop_service(name)
                        _start_service(name)
                    st.rerun()

                if b_stop.button("⬛ Stop", key=f"stop_{name}", use_container_width=True):
                    if svc["managed"]:
                        _stop_service(name)
                    st.rerun()

                chosen = dev_col.selectbox(
                    "Device",
                    svc["devices"],
                    index=svc["devices"].index(
                        st.session_state.get(f"device_{name}", "auto")
                    ),
                    key=f"device_{name}",
                    label_visibility="collapsed",
                )

                active_label = _active_device_label(chosen)
                act_col.markdown(
                    f'<span class="badge badge-green">Active: {active_label}</span>',
                    unsafe_allow_html=True,
                )

    with right:
        st.subheader("Server Status")

        for name in _SERVICES:
            connected = _is_connected(name)
            dot_cls = "dot-green" if connected else "dot-red"
            dot_label = "Connected" if connected else "Disconnected"
            c1, c2 = st.columns([3, 2])
            c1.write(name)
            c2.markdown(
                f'<span class="{dot_cls}">●</span> {dot_label}',
                unsafe_allow_html=True,
            )

        st.divider()

        # Device/model badges
        try:
            import torch

            if torch.backends.mps.is_available():
                device_badge = "MLX (METAL)"
            elif torch.cuda.is_available():
                device_badge = "CUDA"
            else:
                device_badge = "CPU"
        except ImportError:
            device_badge = "CPU"

        st.markdown(
            f'<span class="badge badge-green">Model Ready</span>'
            f'<span class="badge badge-green">Device: {device_badge}</span>',
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        keep = st.toggle(
            "Keep servers running when app closes",
            value=st.session_state.get("keep_running", False),
            key="keep_running",
        )
        if keep:
            st.caption(
                "When enabled, the backend will continue running "
                "in the background after closing the app."
            )

# ── Page navigation ───────────────────────────────────────────────────────────

st.sidebar.markdown("## Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Analyse Paper", "Server Management"],
    label_visibility="collapsed",
)

if page == "Server Management":
    st.title("Research Analyser")
    show_server_management()
    st.stop()

# ── Analyse Paper page ────────────────────────────────────────────────────────
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
generate_audio = st.sidebar.checkbox("Generate Audio Narration (Qwen3-TTS)", value=False)
diagram_types = st.sidebar.multiselect(
    "Diagram Types",
    ["methodology", "architecture", "results"],
    default=["methodology"],
)
diagram_provider = st.sidebar.selectbox(
    "Diagram Provider",
    ["gemini", "openrouter"],
    index=0,
    help="PaperBanana VLM provider for diagram generation",
)
venue = st.sidebar.text_input("Target Venue (optional)", placeholder="e.g., ICLR 2026")
_default_output = os.environ.get(
    "RESEARCH_ANALYSER_OUTPUT_DIR",
    str(Path.home() / "ResearchAnalyserOutput"),
)
output_dir = st.sidebar.text_input("Output Directory", value=_default_output)

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
            generate_audio=generate_audio,
            diagram_types=diagram_types,
        )

        from research_analyser.analyser import ResearchAnalyser  # deferred heavy import
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
                    from research_analyser.reviewer import interpret_score  # deferred
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

                # Audio Narration
                if generate_audio:
                    audio_file = Path(output_dir) / "analysis_audio.wav"
                    if audio_file.exists():
                        st.subheader("Audio Narration (Qwen3-TTS)")
                        st.audio(str(audio_file), format="audio/wav")
                        with open(audio_file, "rb") as af:
                            st.download_button(
                                "Download Audio Narration (WAV)",
                                af.read(),
                                file_name="analysis_audio.wav",
                                mime="audio/wav",
                            )

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
        from research_analyser.comparison import (  # deferred heavy import
            ReviewSnapshot,
            build_comparison_markdown,
            parse_local_review,
        )
        from research_analyser.reviewer import interpret_score  # deferred
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
