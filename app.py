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

# ── Custom CSS ────────────────────────────────────────────────────────────────
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

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_OUTPUT = os.environ.get(
    "RESEARCH_ANALYSER_OUTPUT_DIR",
    str(Path.home() / "ResearchAnalyserOutput"),
)
_DEFAULT_TEMP = os.environ.get(
    "RESEARCH_ANALYSER_APP__TEMP_DIR",
    str(Path.home() / "ResearchAnalyserOutput" / "tmp"),
)


def _cfg(key: str, default=None):
    """Read a configuration value from session_state."""
    return st.session_state.get(f"cfg_{key}", default)


# ── Server Management helpers ─────────────────────────────────────────────────

_SERVICES: dict[str, dict] = {
    "Analysis API": {
        "url": "http://127.0.0.1:8000",
        "health": "http://127.0.0.1:8000/api/v1/health",
        "cmd": [
            sys.executable, "-m", "uvicorn",
            "research_analyser.api:app",
            "--host", "127.0.0.1", "--port", "8000",
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
    return True  # in-process services are always available


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


# ── Page: Server Management ───────────────────────────────────────────────────

def show_server_management() -> None:
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Server Management")

        for name, svc in _SERVICES.items():
            connected = _is_connected(name)
            dot_cls = "dot-green" if connected else "dot-red"
            dot_label = "Connected" if connected else "Disconnected"

            with st.container(border=True):
                hdr_l, hdr_r = st.columns([4, 2])
                hdr_l.markdown(f"**{name}**")
                hdr_r.markdown(
                    f'<span class="{dot_cls}">●</span> {dot_label}',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<p class="svc-url">{svc["url"]}</p>', unsafe_allow_html=True
                )

                b_restart, b_stop, _, dev_col, act_col = st.columns([1.1, 1, 0.3, 1.8, 2])

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
                act_col.markdown(
                    f'<span class="badge badge-green">Active: {_active_device_label(chosen)}</span>',
                    unsafe_allow_html=True,
                )

    with right:
        st.subheader("Server Status")

        for name in _SERVICES:
            connected = _is_connected(name)
            c1, c2 = st.columns([3, 2])
            c1.write(name)
            c2.markdown(
                f'<span class="{"dot-green" if connected else "dot-red"}">●</span> '
                f'{"Connected" if connected else "Disconnected"}',
                unsafe_allow_html=True,
            )

        st.divider()

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
            st.caption("Backend continues running after the window is closed.")


# ── Page: Configuration ───────────────────────────────────────────────────────

def show_configuration() -> None:
    st.subheader("Configuration")
    st.caption("Settings are saved for the current session. Restart the app to reload from environment variables.")

    # ── API Keys ──────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**API Keys**")
        k1, k2 = st.columns(2)
        st.session_state["cfg_google_key"] = k1.text_input(
            "Google API Key",
            value=_cfg("google_key", os.environ.get("GOOGLE_API_KEY", "")),
            type="password",
            help="Required for PaperBanana diagram generation (Gemini models)",
        )
        st.session_state["cfg_openai_key"] = k2.text_input(
            "OpenAI API Key",
            value=_cfg("openai_key", os.environ.get("OPENAI_API_KEY", "")),
            type="password",
            help="Required for agentic peer review (GPT-4o)",
        )
        k3, k4 = st.columns(2)
        st.session_state["cfg_tavily_key"] = k3.text_input(
            "Tavily API Key",
            value=_cfg("tavily_key", os.environ.get("TAVILY_API_KEY", "")),
            type="password",
            help="Enables related-work search during peer review",
        )
        st.session_state["cfg_hf_token"] = k4.text_input(
            "HuggingFace Token",
            value=_cfg("hf_token", os.environ.get("HF_TOKEN", "")),
            type="password",
            help="Required for Qwen3-TTS model download",
        )

    # ── OCR Model ─────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**OCR Model**")
        c1, c2 = st.columns(2)
        st.session_state["cfg_ocr_model"] = c1.selectbox(
            "MonkeyOCR Model",
            ["MonkeyOCR-pro-3B", "MonkeyOCR-pro-1.2B"],
            index=["MonkeyOCR-pro-3B", "MonkeyOCR-pro-1.2B"].index(
                _cfg("ocr_model", "MonkeyOCR-pro-3B")
            ),
            help="3B: higher accuracy, 1.2B: faster",
        )
        st.session_state["cfg_ocr_device"] = c2.selectbox(
            "OCR Device",
            ["auto", "mps", "cuda", "cpu"],
            index=["auto", "mps", "cuda", "cpu"].index(_cfg("ocr_device", "auto")),
        )

    # ── Review Model ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Review Model**")
        c1, c2 = st.columns(2)
        _review_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4"]
        st.session_state["cfg_review_model"] = c1.selectbox(
            "LLM Model",
            _review_models,
            index=_review_models.index(_cfg("review_model", "gpt-4o")),
            help="Model for agentic peer review",
        )
        st.session_state["cfg_use_tavily"] = c2.toggle(
            "Use Tavily for related-work search",
            value=_cfg("use_tavily", True),
        )

    # ── Diagram / VLM Settings ────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Diagram Generation**")
        c1, c2, c3 = st.columns(3)
        st.session_state["cfg_diagram_provider"] = c1.selectbox(
            "Provider",
            ["gemini", "openrouter"],
            index=["gemini", "openrouter"].index(_cfg("diagram_provider", "gemini")),
            help="PaperBanana VLM provider",
        )
        st.session_state["cfg_vlm_model"] = c2.text_input(
            "VLM Model",
            value=_cfg("vlm_model", "gemini-2.0-flash"),
            help="Vision-language model for diagram planning",
        )
        st.session_state["cfg_image_model"] = c3.text_input(
            "Image Model",
            value=_cfg("image_model", "gemini-3-pro-image-preview"),
            help="Image generation model",
        )

    # ── STORM Settings ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**STORM Wikipedia-style Report**")
        c1, c2 = st.columns([1, 3])
        st.session_state["cfg_storm_enabled"] = c1.toggle(
            "Enable STORM",
            value=_cfg("storm_enabled", False),
        )
        if _cfg("storm_enabled", False):
            sc1, sc2, sc3 = c2.columns(3)
            st.session_state["cfg_storm_conv_model"] = sc1.selectbox(
                "Conv model", ["gpt-4o-mini", "gpt-4o"],
                index=["gpt-4o-mini", "gpt-4o"].index(_cfg("storm_conv_model", "gpt-4o-mini")),
            )
            st.session_state["cfg_storm_outline_model"] = sc2.selectbox(
                "Outline model", ["gpt-4o", "gpt-4o-mini"],
                index=["gpt-4o", "gpt-4o-mini"].index(_cfg("storm_outline_model", "gpt-4o")),
            )
            st.session_state["cfg_storm_article_model"] = sc3.selectbox(
                "Article model", ["gpt-4o", "gpt-4o-mini"],
                index=["gpt-4o", "gpt-4o-mini"].index(_cfg("storm_article_model", "gpt-4o")),
            )

    # ── TTS Settings ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Text-to-Speech Narration**")
        st.session_state["cfg_tts_enabled"] = st.toggle(
            "Enable Qwen3-TTS audio narration",
            value=_cfg("tts_enabled", False),
            help="Requires HF_TOKEN and soundfile. Generates a WAV narration of the report.",
        )

    # ── Output Paths ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Output Paths**")
        c1, c2 = st.columns(2)
        st.session_state["cfg_output_dir"] = c1.text_input(
            "Output Directory",
            value=_cfg("output_dir", _DEFAULT_OUTPUT),
        )
        st.session_state["cfg_temp_dir"] = c2.text_input(
            "Temp Directory",
            value=_cfg("temp_dir", _DEFAULT_TEMP),
        )

    # ── Target Venue ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Review Target**")
        st.session_state["cfg_venue"] = st.text_input(
            "Target Venue (optional)",
            value=_cfg("venue", ""),
            placeholder="e.g., ICLR 2026",
            help="Used to tailor the peer review to a specific conference or journal",
        )


# ── Page navigation ───────────────────────────────────────────────────────────

st.sidebar.markdown("## Research Analyser")
page = st.sidebar.radio(
    "Navigate",
    ["Analyse Paper", "Configuration", "Server Management"],
    label_visibility="collapsed",
)

if page == "Server Management":
    st.title("Research Analyser")
    show_server_management()
    st.stop()

if page == "Configuration":
    st.title("Research Analyser")
    show_configuration()
    st.stop()

# ── Page: Analyse Paper ───────────────────────────────────────────────────────

st.title("Research Analyser")
st.markdown("AI-powered research paper analysis with OCR, diagram generation, and peer review.")

# ── Per-run Analysis Options (inline, above input) ────────────────────────────
with st.container(border=True):
    st.markdown("**Analysis Options**")
    opt_c1, opt_c2, opt_c3, opt_c4, opt_c5 = st.columns(5)
    generate_diagrams = opt_c1.checkbox("Diagrams", value=True)
    generate_review   = opt_c2.checkbox("Peer Review", value=True)
    generate_audio    = opt_c3.checkbox("Audio (TTS)", value=_cfg("tts_enabled", False))
    generate_storm    = opt_c4.checkbox("STORM Report", value=_cfg("storm_enabled", False))

    diagram_types = opt_c5.multiselect(
        "Diagram types",
        ["methodology", "architecture", "results"],
        default=["methodology"],
        label_visibility="visible",
    )

# ── Input area ────────────────────────────────────────────────────────────────
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

# ── Run Analysis ──────────────────────────────────────────────────────────────
if st.button("Analyse Paper", type="primary", use_container_width=True):
    if not source and not uploaded_file:
        st.error("Please upload a PDF or enter a paper URL.")
    else:
        # Read config from session state (set on Configuration page)
        google_api_key  = _cfg("google_key",  os.environ.get("GOOGLE_API_KEY", ""))
        openai_api_key  = _cfg("openai_key",  os.environ.get("OPENAI_API_KEY", ""))
        tavily_api_key  = _cfg("tavily_key",  os.environ.get("TAVILY_API_KEY", ""))
        hf_token        = _cfg("hf_token",    os.environ.get("HF_TOKEN", ""))
        output_dir      = _cfg("output_dir",  _DEFAULT_OUTPUT)
        temp_dir        = _cfg("temp_dir",    _DEFAULT_TEMP)

        # Push API keys into environment for downstream libraries
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        if tavily_api_key:
            os.environ["TAVILY_API_KEY"] = tavily_api_key
        if hf_token:
            os.environ["HF_TOKEN"] = hf_token

        config = Config.load()
        config.app.output_dir = output_dir
        config.app.temp_dir   = temp_dir
        config.diagrams.provider  = _cfg("diagram_provider", "gemini")
        config.diagrams.vlm_model = _cfg("vlm_model", "gemini-2.0-flash")
        config.ocr.model          = _cfg("ocr_model", "MonkeyOCR-pro-3B")
        config.ocr.device         = _cfg("ocr_device", "auto")
        config.review.model       = _cfg("review_model", "gpt-4o")
        config.review.use_tavily  = _cfg("use_tavily", True)
        config.storm.enabled      = generate_storm
        if generate_storm:
            config.storm.conv_model    = _cfg("storm_conv_model", "gpt-4o-mini")
            config.storm.outline_model = _cfg("storm_outline_model", "gpt-4o")
            config.storm.article_model = _cfg("storm_article_model", "gpt-4o")
        config.tts.enabled = generate_audio

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
            generate_storm_report=generate_storm,
            diagram_types=diagram_types,
        )

        from research_analyser.analyser import ResearchAnalyser  # deferred heavy import
        analyser = ResearchAnalyser(config=config)

        # Handle file upload
        if uploaded_file:
            tmp_path = Path(temp_dir) / "uploads"
            tmp_path.mkdir(parents=True, exist_ok=True)
            file_path = tmp_path / uploaded_file.name
            file_path.write_bytes(uploaded_file.read())
            source = str(file_path)

        with st.spinner("Analysing paper… This may take a few minutes."):
            try:
                report = asyncio.run(analyser.analyse(source, options=options))

                st.header("Analysis Results")

                st.subheader(report.extracted_content.title)
                if report.extracted_content.authors:
                    st.write(f"**Authors:** {', '.join(report.extracted_content.authors)}")

                if report.summary:
                    st.subheader("Summary")
                    st.write(report.summary.one_sentence)
                    with st.expander("Full Summary"):
                        st.write(report.summary.abstract_summary)
                        st.write("**Methodology:**", report.summary.methodology_summary)
                        st.write("**Results:**", report.summary.results_summary)

                if report.key_points:
                    st.subheader("Key Findings")
                    for kp in report.key_points:
                        with st.expander(
                            f"{'🔴' if kp.importance == 'high' else '🟡'} {kp.point}"
                        ):
                            st.write(f"**Evidence:** {kp.evidence}")
                            st.write(f"**Section:** {kp.section}")

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Equations", len(report.extracted_content.equations))
                col2.metric("Tables",    len(report.extracted_content.tables))
                col3.metric("Figures",   len(report.extracted_content.figures))
                col4.metric("References",len(report.extracted_content.references))

                display_eqs = [e for e in report.extracted_content.equations if not e.is_inline]
                if display_eqs:
                    st.subheader("Key Equations")
                    for eq in display_eqs[:10]:
                        with st.expander(f"Equation: {eq.label or eq.id}"):
                            st.latex(eq.latex)
                            st.write(f"**Section:** {eq.section}")
                            if eq.description:
                                st.write(f"**Description:** {eq.description}")

                if report.diagrams:
                    st.subheader("Generated Diagrams")
                    for diagram in report.diagrams:
                        st.write(f"**{diagram.diagram_type.title()}**")
                        if Path(diagram.image_path).exists():
                            st.image(diagram.image_path, caption=diagram.caption)
                        else:
                            st.info(f"Diagram saved to: {diagram.image_path}")

                if report.review:
                    from research_analyser.reviewer import interpret_score  # deferred
                    st.subheader("Peer Review")
                    score = report.review.overall_score
                    decision = interpret_score(score)

                    col_s, col_d, col_c = st.columns(3)
                    col_s.metric("Overall Score", f"{score:.1f}/10")
                    col_d.metric("Decision", decision)
                    col_c.metric("Confidence", f"{report.review.confidence:.0f}/5")

                    st.write("**Dimensional Scores:**")
                    for dim_name, dim in report.review.dimensions.items():
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

                if generate_storm and report.storm_report:
                    st.subheader("STORM Report")
                    with st.expander("View Wikipedia-style article"):
                        st.markdown(report.storm_report)
                    st.download_button(
                        "Download STORM Report (Markdown)",
                        report.storm_report,
                        file_name="storm_report.md",
                        mime="text/markdown",
                    )

                st.subheader("Download Reports")
                report_md = report.to_markdown()
                st.download_button(
                    "Download Full Report (Markdown)",
                    report_md,
                    file_name="analysis_report.md",
                    mime="text/markdown",
                )
                st.success(f"All outputs saved to: {output_dir}")
                st.session_state["last_report"] = report

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                st.exception(e)


# ── PaperReview.ai Comparison ────────────────────────────────────────────────
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

        ext_data = json.loads(ext_file.getvalue().decode("utf-8"))
        external = ReviewSnapshot(
            source=f"paperreview.ai:{ext_file.name}",
            overall_score=ext_data.get("overall_score") or ext_data.get("review_score") or ext_data.get("overall"),
            soundness=ext_data.get("soundness"),
            presentation=ext_data.get("presentation"),
            contribution=ext_data.get("contribution"),
            confidence=ext_data.get("confidence"),
        )

        st.subheader("External Review (PaperReview.ai)")
        ec = st.columns(5)
        ec[0].metric("Overall",      f"{external.overall_score:.1f}/10"  if external.overall_score  else "n/a")
        ec[1].metric("Soundness",    f"{external.soundness:.1f}/4"        if external.soundness       else "n/a")
        ec[2].metric("Presentation", f"{external.presentation:.1f}/4"     if external.presentation    else "n/a")
        ec[3].metric("Contribution", f"{external.contribution:.1f}/4"     if external.contribution    else "n/a")
        ec[4].metric("Confidence",   f"{external.confidence:.1f}/5"       if external.confidence      else "n/a")

        if external.overall_score is not None:
            st.info(f"**PaperReview.ai Decision:** {interpret_score(external.overall_score)}")

        last_report = st.session_state.get("last_report")
        output_dir  = _cfg("output_dir", _DEFAULT_OUTPUT)
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
