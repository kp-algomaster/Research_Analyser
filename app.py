"""Streamlit Web UI for Research Analyser."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# Load .env before anything else so GOOGLE_API_KEY etc. are available.
# When running inside the macOS .app bundle the CWD is not the project dir,
# so explicitly check the companion app-support dir first.
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    _dotenv_candidates = [
        _Path.home() / ".researchanalyser" / ".env",  # DMG install (primary)
        _Path.home() / ".env",                         # home dir fallback
        _Path(__file__).resolve().parent / ".env",     # project root (dev mode)
    ]
    for _dp in _dotenv_candidates:
        if _dp.exists():
            load_dotenv(_dp, override=False)
    # Also let load_dotenv search from CWD upwards as a final catch-all
    load_dotenv(override=False)
except ImportError:
    pass

import streamlit as st

from research_analyser.config import Config
from research_analyser.models import AnalysisOptions

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Research Analyser",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
#MainMenu, footer, header { visibility: hidden; }
.stApp { background: #0d1117; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #161b22 !important;
    border-right: 1px solid #21262d !important;
}
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span {
    color: #e6edf3 !important;
}
[data-testid="stSidebar"] .stMarkdown h2 {
    font-size: 15px !important; font-weight: 700 !important; margin: 0 !important;
}

/* ── Sidebar nav buttons ── */
/* Use st.sidebar.button() — text lives directly in <button>, no selector guessing */
[data-testid="stSidebar"] .stButton { margin-bottom: 1px !important; }
[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 10px 16px !important;
    border-radius: 9px !important;
    font-size: 14px !important;
    letter-spacing: 0.01em !important;
    transition: background 0.15s, color 0.15s !important;
    width: 100% !important;
    box-shadow: none !important;
    transform: none !important;
}
/* Inactive nav button */
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    background: transparent !important;
    border: none !important;
    color: #e6edf3 !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
    background: #21262d !important;
    color: #ffffff !important;
    border: none !important;
}
/* Active nav button */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #1f2d47 !important;
    border: 1px solid #1f3d6e !important;
    color: #58a6ff !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: #1f2d47 !important;
    color: #79b8ff !important;
    transform: none !important;
    box-shadow: none !important;
}

/* Sidebar caption text */
[data-testid="stSidebar"] .stCaption p,
[data-testid="stSidebar"] .stCaption {
    color: #8b949e !important;
    font-size: 12px !important;
}

/* ── Page hero ── */
.hero {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 40%, #0f1b2d 100%);
    border: 1px solid #21262d; border-radius: 14px;
    padding: 28px 32px; margin-bottom: 24px;
    position: relative; overflow: hidden;
}
.hero::before {
    content: ""; position: absolute; top: -80px; right: -80px;
    width: 280px; height: 280px;
    background: radial-gradient(circle, rgba(56,139,253,0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-title {
    font-size: 26px; font-weight: 800; margin: 0 0 6px 0;
    background: linear-gradient(90deg, #58a6ff, #bc8cff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-sub { color: #c9d1d9; font-size: 13.5px; margin: 0; line-height: 1.6; }

/* ── Section label ── */
.sec-label {
    font-size: 11px; font-weight: 700; letter-spacing: 0.10em;
    color: #58a6ff; text-transform: uppercase; margin: 18px 0 10px 0;
}

/* ── Containers (border override) ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #161b22 !important;
    border-color: #21262d !important;
    border-radius: 12px !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #161b22 !important;
    border-bottom: 1px solid #21262d !important;
    padding: 0 !important; gap: 0 !important;
    border-radius: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #e6edf3 !important; font-size: 13px !important;
    font-weight: 500 !important; padding: 10px 20px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #f0f6fc !important; }
.stTabs [aria-selected="true"] {
    color: #58a6ff !important; font-weight: 700 !important;
    border-bottom: 2px solid #58a6ff !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-top: none !important;
    border-radius: 0 0 12px 12px !important;
    padding: 20px !important;
}
/* wrap parent */
.stTabs { background: transparent !important; border-radius: 12px 12px 12px 12px; overflow: hidden; }

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #161b22 !important; border: 1px solid #21262d !important;
    border-radius: 10px !important; padding: 14px 18px !important;
}
[data-testid="stMetricValue"] { font-size: 26px !important; color: #f0f6fc !important; font-weight: 800 !important; }
[data-testid="stMetricLabel"] { color: #e6edf3 !important; font-size: 11px !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.06em !important; }

/* ── Buttons ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #388bfd, #7c3aed) !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; font-size: 14px !important;
    padding: 10px 20px !important; letter-spacing: 0.02em !important;
    box-shadow: 0 2px 16px rgba(56,139,253,0.25) !important;
    transition: all 0.2s !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 24px rgba(56,139,253,0.4) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: #21262d !important; border: 1px solid #30363d !important;
    color: #c9d1d9 !important; border-radius: 8px !important;
    font-size: 13px !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #58a6ff !important; color: #f0f6fc !important;
}

/* ── File uploader ── */
[data-testid="stFileUploaderDropzone"] {
    background: #161b22 !important; border: 2px dashed #21262d !important;
    border-radius: 12px !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #388bfd !important; background: #0f1b2d !important;
}

/* ── Inputs ── */
.stTextInput > div > div > input,
.stSelectbox > div > div > div,
.stMultiSelect > div > div {
    background: #0d1117 !important; border-color: #30363d !important;
    color: #f0f6fc !important; border-radius: 8px !important;
}
.stTextInput > div > div > input:focus {
    border-color: #388bfd !important;
    box-shadow: 0 0 0 2px rgba(56,139,253,0.15) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #161b22 !important; border: 1px solid #21262d !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] > details > summary {
    color: #c9d1d9 !important; font-size: 13px !important;
}
[data-testid="stExpander"] > details > summary:hover { color: #f0f6fc !important; }
/* Expander body text — nuclear wildcard on the body-only node */
[data-testid="stExpanderDetails"] *,
[data-testid="stExpander"] details > div * {
    color: #ffffff !important;
}
/* Keep expander header readable (not the body) */
[data-testid="stExpander"] > details > summary,
[data-testid="stExpander"] > details > summary * {
    color: #c9d1d9 !important;
}
[data-testid="stExpander"] > details > summary:hover,
[data-testid="stExpander"] > details > summary:hover * {
    color: #f0f6fc !important;
}

/* ── Progress bars ── */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #388bfd, #8957e5) !important;
}
[data-testid="stProgressBar"] { border-radius: 99px !important; }

/* ── Divider ── */
hr { border-color: #21262d !important; margin: 20px 0 !important; }

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: 10px !important; border-left-width: 3px !important; }

/* ── Checkboxes / toggles ── */
.stCheckbox > label, .stToggle > label { font-size: 13.5px !important; color: #e6edf3 !important; font-weight: 500 !important; }
.stCheckbox > label:hover, .stToggle > label:hover { color: #f0f6fc !important; }

/* ── Pills (st.pills diagram type chips) ── */
[data-testid="stPills"] button {
    background: #21262d !important; border: 1px solid #30363d !important;
    color: #8b949e !important; border-radius: 99px !important;
    font-size: 12.5px !important; font-weight: 600 !important;
    padding: 5px 14px !important; transition: all 0.15s !important;
}
[data-testid="stPills"] button:hover {
    border-color: #58a6ff !important; color: #c9d1d9 !important;
    background: #1f2d47 !important;
}
[data-testid="stPills"] button[aria-selected="true"],
[data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stPills"] button[data-selected="true"] {
    background: #1f2d47 !important; border-color: #388bfd !important;
    color: #58a6ff !important;
}
[data-testid="stPills"] > label {
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.08em !important; text-transform: uppercase !important;
    color: #58a6ff !important;
}

/* ── Custom badge + dot ── */
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.78rem; font-weight: 600; margin-right: 4px;
}
.badge-green  { background: #0d2d1a; color: #3fb950; border: 1px solid #238636; }
.badge-blue   { background: #0f1b2d; color: #58a6ff; border: 1px solid #1f3d6e; }
.badge-purple { background: #1e1b4b; color: #bc8cff; border: 1px solid #3d2b6e; }
.badge-gray   { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
.dot-green { color: #3fb950; }
.dot-red   { color: #f85149; }
.svc-url   { font-size: 0.78rem; color: #8b949e; margin-top: -6px; }

/* ── Paper result card ── */
.paper-card {
    background: #161b22; border: 1px solid #21262d;
    border-left: 4px solid #388bfd; border-radius: 0 12px 12px 0;
    padding: 18px 22px; margin-bottom: 18px;
}
.paper-title  { font-size: 18px; font-weight: 700; color: #f0f6fc; margin: 0 0 6px 0; line-height: 1.3; }
.paper-meta   { font-size: 12px; color: #c9d1d9; }
.paper-chip   {
    display: inline-block; background: #1f2d47; color: #58a6ff;
    border: 1px solid #1f3d6e; border-radius: 99px;
    font-size: 11px; font-weight: 600; padding: 2px 10px; margin-right: 6px;
}

/* ── Score display ── */
.score-block {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #0f1b2d, #1e1b4b);
    border: 2px solid #388bfd; border-radius: 14px;
    padding: 16px; min-width: 90px;
}
.score-num   { font-size: 32px; font-weight: 800; color: #58a6ff; line-height: 1; }
.score-denom { font-size: 12px; color: #8b949e; margin-top: 2px; }

/* ── Decision pill ── */
.decision-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 18px; border-radius: 99px;
    font-size: 13px; font-weight: 700;
}
.pill-accept { background: #0d2d1a; color: #3fb950; border: 1px solid #238636; }
.pill-weak   { background: #2d1b00; color: #f0883e; border: 1px solid #6e3a1e; }
.pill-reject { background: #2d0f0f; color: #f85149; border: 1px solid #6e2020; }

/* ── Dim score bar ── */
.dimbar { margin-bottom: 12px; }
.dimbar-header { display: flex; justify-content: space-between; margin-bottom: 5px; }
.dimbar-name   { font-size: 12px; color: #c9d1d9; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.dimbar-val    { font-size: 12px; font-weight: 700; color: #58a6ff; }
.dimbar-track  { height: 5px; background: #21262d; border-radius: 99px; overflow: hidden; }
.dimbar-fill   { height: 100%; background: linear-gradient(90deg, #388bfd, #8957e5); border-radius: 99px; }

/* ── SW item ── */
.sw-row { display: flex; gap: 8px; padding: 8px 0; border-bottom: 1px solid #21262d; font-size: 13px; color: #c9d1d9; align-items: flex-start; }
.sw-row:last-child { border-bottom: none; }
.sw-icon { flex-shrink: 0; margin-top: 1px; }

/* ── Config card header ── */
.cfg-hdr {
    display: flex; align-items: center; gap: 10px;
    font-size: 14px; font-weight: 700; color: #f0f6fc;
    margin: 0 0 14px 0;
}
.cfg-icon {
    width: 30px; height: 30px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px;
}
.cfg-icon-key    { background: #1f2d47; }
.cfg-icon-ocr    { background: #1e2d1a; }
.cfg-icon-review { background: #2d1b00; }
.cfg-icon-diag   { background: #1e1b4b; }
.cfg-icon-storm  { background: #0d2d1a; }
.cfg-icon-tts    { background: #2d1218; }
.cfg-icon-path   { background: #21262d; }
.cfg-icon-venue  { background: #1f2d47; }
</style>
""", unsafe_allow_html=True)

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
    return st.session_state.get(f"cfg_{key}", default)


# ── Helpers: HTML components ──────────────────────────────────────────────────

def _dimbar(name: str, score: float, max_score: float = 4.0) -> str:
    pct = min(score / max_score * 100, 100)
    return (
        f'<div class="dimbar">'
        f'  <div class="dimbar-header">'
        f'    <span class="dimbar-name">{name}</span>'
        f'    <span class="dimbar-val">{score:.1f} / {max_score:.0f}</span>'
        f'  </div>'
        f'  <div class="dimbar-track">'
        f'    <div class="dimbar-fill" style="width:{pct:.1f}%"></div>'
        f'  </div>'
        f'</div>'
    )


def _decision_pill(decision: str, score: float) -> str:
    cls = "pill-accept" if score >= 6.5 else ("pill-weak" if score >= 4.5 else "pill-reject")
    icon = "✓" if score >= 6.5 else ("△" if score >= 4.5 else "✗")
    return f'<span class="decision-pill {cls}">{icon} {decision}</span>'


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
    return True


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
    st.markdown('<div class="hero"><p class="hero-title">Server Management</p><p class="hero-sub">Monitor and control backend services</p></div>', unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown('<p class="sec-label">Services</p>', unsafe_allow_html=True)
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
                st.markdown(f'<p class="svc-url">{svc["url"]}</p>', unsafe_allow_html=True)

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
                    "Device", svc["devices"],
                    index=svc["devices"].index(st.session_state.get(f"device_{name}", "auto")),
                    key=f"device_{name}", label_visibility="collapsed",
                )
                act_col.markdown(
                    f'<span class="badge badge-green">⚡ {_active_device_label(chosen)}</span>',
                    unsafe_allow_html=True,
                )

    with right:
        st.markdown('<p class="sec-label">Status Overview</p>', unsafe_allow_html=True)
        with st.container(border=True):
            for name in _SERVICES:
                connected = _is_connected(name)
                c1, c2 = st.columns([3, 2])
                c1.markdown(f'<span style="font-size:13px;color:#c9d1d9">{name}</span>', unsafe_allow_html=True)
                c2.markdown(
                    f'<span class="{"dot-green" if connected else "dot-red"}">●</span> '
                    f'<span style="font-size:12px;color:#{"3fb950" if connected else "f85149"}">'
                    f'{"Online" if connected else "Offline"}</span>',
                    unsafe_allow_html=True,
                )

            st.divider()

            try:
                import torch
                if torch.backends.mps.is_available():
                    device_badge, badge_cls = "MLX (METAL)", "badge-green"
                elif torch.cuda.is_available():
                    device_badge, badge_cls = "CUDA", "badge-blue"
                else:
                    device_badge, badge_cls = "CPU", "badge-gray"
            except ImportError:
                device_badge, badge_cls = "CPU", "badge-gray"

            st.markdown(
                f'<span class="badge badge-green">● Ready</span>'
                f'<span class="badge {badge_cls}">⚡ {device_badge}</span>',
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
            keep = st.toggle(
                "Keep servers running on close",
                value=st.session_state.get("keep_running", False),
                key="keep_running",
            )
            if keep:
                st.caption("Backend continues running after the window is closed.")


# ── Page: Configuration ───────────────────────────────────────────────────────

def show_configuration() -> None:
    st.markdown('<div class="hero"><p class="hero-title">Configuration</p><p class="hero-sub">Settings persist for the current session. For persistence across restarts, put your API keys in <code>~/.researchanalyser/.env</code> (e.g. <code>GOOGLE_API_KEY=…</code>).</p></div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2, gap="medium")

    with col_a:
        # API Keys
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-key">🔑</div>API Keys</div>', unsafe_allow_html=True)
            st.session_state["cfg_google_key"] = st.text_input(
                "Google API Key", value=_cfg("google_key", os.environ.get("GOOGLE_API_KEY", "")),
                type="password", help="Required for PaperBanana diagram generation (Gemini)",
            )
            st.session_state["cfg_openai_key"] = st.text_input(
                "OpenAI API Key", value=_cfg("openai_key", os.environ.get("OPENAI_API_KEY", "")),
                type="password", help="Required for agentic peer review (GPT-4o)",
            )
            st.session_state["cfg_tavily_key"] = st.text_input(
                "Tavily API Key", value=_cfg("tavily_key", os.environ.get("TAVILY_API_KEY", "")),
                type="password", help="Enables related-work search during peer review",
            )
            st.session_state["cfg_hf_token"] = st.text_input(
                "HuggingFace Token", value=_cfg("hf_token", os.environ.get("HF_TOKEN", "")),
                type="password", help="Required for Qwen3-TTS model download",
            )

        # OCR
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-ocr">📄</div>OCR Engine</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            st.session_state["cfg_ocr_model"] = c1.selectbox(
                "Model variant",
                ["MonkeyOCR-pro-3B", "MonkeyOCR-pro-1.2B"],
                index=["MonkeyOCR-pro-3B", "MonkeyOCR-pro-1.2B"].index(_cfg("ocr_model", "MonkeyOCR-pro-3B")),
                help="3B: higher accuracy · 1.2B: faster",
            )
            st.session_state["cfg_ocr_device"] = c2.selectbox(
                "Device",
                ["auto", "mps", "cuda", "cpu"],
                index=["auto", "mps", "cuda", "cpu"].index(_cfg("ocr_device", "auto")),
            )

        # Review model
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-review">🧐</div>Review Model</div>', unsafe_allow_html=True)
            _rm = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4"]
            c1, c2 = st.columns(2)
            st.session_state["cfg_review_model"] = c1.selectbox(
                "LLM", _rm, index=_rm.index(_cfg("review_model", "gpt-4o")),
                help="Model for the 9-node agentic peer review",
            )
            st.session_state["cfg_use_tavily"] = c2.toggle(
                "Tavily related-work search", value=_cfg("use_tavily", True),
            )

    with col_b:
        # Diagrams
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-diag">🎨</div>Diagram Generation</div>', unsafe_allow_html=True)

            # ── PaperBanana installation status ────────────────────────────
            try:
                import paperbanana as _pb  # noqa
                _pb_version = getattr(_pb, "__version__", "")
                _pb_label = f"PaperBanana {_pb_version}".strip()
                _pb_ok = True
            except ImportError:
                _pb_ok = False
                _pb_label = "PaperBanana not installed"

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">'
                f'  <span style="font-size:12px;color:#8b949e;font-weight:600;text-transform:uppercase;letter-spacing:.06em">Engine</span>'
                f'  <span class="badge {"badge-green" if _pb_ok else "badge-gray"}">'
                f'    {"✓" if _pb_ok else "✗"} {_pb_label}'
                f'  </span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if not _pb_ok:
                st.warning(
                    "**PaperBanana is not installed** — diagrams will fall back to matplotlib.\n\n"
                    "Install once inside the app's companion venv:\n"
                    "```\npip install 'paperbanana[dev,openai,google] @ "
                    "git+https://github.com/llmsresearch/paperbanana.git'\n```\n"
                    "Then restart the app. The installer will do this automatically on next launch."
                )

            c1, c2 = st.columns(2)
            st.session_state["cfg_diagram_provider"] = c1.selectbox(
                "LLM Provider", ["gemini", "openrouter"],
                index=["gemini", "openrouter"].index(_cfg("diagram_provider", "gemini")),
                help="Provider PaperBanana uses for vision-language planning",
            )
            st.session_state["cfg_vlm_model"] = c2.text_input(
                "VLM model", value=_cfg("vlm_model", "gemini-2.0-flash"),
                help="Vision-language model for diagram planning",
            )
            st.session_state["cfg_image_model"] = st.text_input(
                "Image model", value=_cfg("image_model", "gemini-3-pro-image-preview"),
                help="Google image model used by PaperBanana (e.g. gemini-3-pro-image-preview · gemini-2.5-flash-image · imagen-4.0-fast-generate-001)",
            )
            c3, c4, c5 = st.columns(3)
            st.session_state["cfg_max_iterations"] = c3.number_input(
                "Refinement iterations", min_value=1, max_value=10,
                value=int(_cfg("max_iterations", 3)),
                help="PaperBanana Critic–Visualizer cycles (more = better quality, slower)",
            )
            st.session_state["cfg_auto_refine"] = c4.toggle(
                "Auto-refine", value=_cfg("auto_refine", True),
                help="Let PaperBanana's Critic agent request revisions automatically",
            )
            st.session_state["cfg_optimize_inputs"] = c5.toggle(
                "Optimize inputs", value=_cfg("optimize_inputs", True),
                help="Retriever stage selects best reference examples for planning",
            )

        # STORM
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-storm">🌪️</div>STORM Report</div>', unsafe_allow_html=True)
            st.session_state["cfg_storm_enabled"] = st.toggle(
                "Enable Wikipedia-style article generation", value=_cfg("storm_enabled", False),
            )
            if _cfg("storm_enabled", False):
                sc1, sc2, sc3 = st.columns(3)
                st.session_state["cfg_storm_conv_model"] = sc1.selectbox(
                    "Conv", ["gpt-4o-mini", "gpt-4o"],
                    index=["gpt-4o-mini", "gpt-4o"].index(_cfg("storm_conv_model", "gpt-4o-mini")),
                )
                st.session_state["cfg_storm_outline_model"] = sc2.selectbox(
                    "Outline", ["gpt-4o", "gpt-4o-mini"],
                    index=["gpt-4o", "gpt-4o-mini"].index(_cfg("storm_outline_model", "gpt-4o")),
                )
                st.session_state["cfg_storm_article_model"] = sc3.selectbox(
                    "Article", ["gpt-4o", "gpt-4o-mini"],
                    index=["gpt-4o", "gpt-4o-mini"].index(_cfg("storm_article_model", "gpt-4o")),
                )

        # TTS
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-tts">🎙️</div>Audio Narration</div>', unsafe_allow_html=True)
            st.session_state["cfg_tts_enabled"] = st.toggle(
                "Enable Qwen3-TTS narration", value=_cfg("tts_enabled", False),
                help="Requires HF_TOKEN · outputs analysis_audio.wav",
            )

            # ── Model cache status & download ──────────────────────────────
            _TTS_MODEL_ID = "Qwen/Qwen3-TTS"
            _hf_cache = Path(
                os.environ.get("HUGGINGFACE_HUB_CACHE",
                               os.environ.get("HF_HOME",
                                              str(Path.home() / ".cache" / "huggingface" / "hub")))
            )
            _model_cache_dir = _hf_cache / ("models--" + _TTS_MODEL_ID.replace("/", "--"))
            _model_cached = _model_cache_dir.exists() and any(_model_cache_dir.rglob("*.safetensors"))

            if _model_cached:
                st.success("✓ Qwen3-TTS model cached locally — no download needed")
            else:
                st.info("Qwen3-TTS not yet downloaded (~3 GB). Download once for offline use.")

            _dl_col1, _dl_col2 = st.columns([3, 1])
            _force_dl = _dl_col2.checkbox("Force re-download", key="tts_force_dl",
                                          disabled=not _model_cached)
            if _dl_col1.button(
                "⬇  Download Qwen3-TTS Model" if not _model_cached else "⬇  Re-download Qwen3-TTS Model",
                disabled=_model_cached and not _force_dl,
                use_container_width=True,
                key="btn_dl_tts",
            ):
                _hf_token = _cfg("hf_token", os.environ.get("HF_TOKEN", ""))
                if not _hf_token:
                    st.error("Set a HuggingFace Token in the API Keys section first.")
                else:
                    try:
                        from huggingface_hub import snapshot_download  # type: ignore
                    except ImportError:
                        st.error(
                            "`huggingface_hub` not installed. "
                            "Run: pip install huggingface-hub"
                        )
                        snapshot_download = None  # type: ignore

                    if snapshot_download is not None:
                        with st.status(
                            f"Downloading {_TTS_MODEL_ID} (~3 GB)…",
                            expanded=True,
                        ) as _dl_status:
                            st.write("Connecting to HuggingFace Hub…")
                            try:
                                snapshot_download(
                                    repo_id=_TTS_MODEL_ID,
                                    token=_hf_token,
                                    ignore_patterns=["*.msgpack", "*.h5", "flax_model*"],
                                )
                                _dl_status.update(
                                    label="✓ Download complete — model cached locally",
                                    state="complete",
                                    expanded=False,
                                )
                                st.rerun()
                            except Exception as _dl_err:
                                _dl_status.update(
                                    label=f"Download failed: {_dl_err}",
                                    state="error",
                                    expanded=True,
                                )
                                st.error(str(_dl_err))

        # Paths
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-path">📁</div>Output Paths</div>', unsafe_allow_html=True)
            st.session_state["cfg_output_dir"] = st.text_input(
                "Output directory", value=_cfg("output_dir", _DEFAULT_OUTPUT),
            )
            st.session_state["cfg_temp_dir"] = st.text_input(
                "Temp directory", value=_cfg("temp_dir", _DEFAULT_TEMP),
            )

        # Venue
        with st.container(border=True):
            st.markdown('<div class="cfg-hdr"><div class="cfg-icon cfg-icon-venue">🏛️</div>Review Target</div>', unsafe_allow_html=True)
            st.session_state["cfg_venue"] = st.text_input(
                "Target venue (optional)", value=_cfg("venue", ""),
                placeholder="e.g., ICLR 2026",
                help="Tailors the peer review to a specific conference or journal",
            )


# ── Sidebar navigation ────────────────────────────────────────────────────────

st.sidebar.markdown("""
<div style="display:flex;align-items:center;gap:10px;padding:4px 0 20px 0">
  <div style="width:34px;height:34px;background:linear-gradient(135deg,#388bfd,#8957e5);
              border-radius:8px;display:flex;align-items:center;justify-content:center;
              font-size:17px;flex-shrink:0">🔬</div>
  <div>
    <div style="font-size:14px;font-weight:700;color:#f0f6fc;line-height:1.2">Research Analyser</div>
    <div style="font-size:11px;color:#c9d1d9">AI Paper Analysis</div>
  </div>
</div>
""", unsafe_allow_html=True)

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "analyse"

_NAV = [
    ("📄  Analyse Paper",    "analyse"),
    ("⚙️  Configuration",     "config"),
    ("🖥️  Server Management", "server"),
]
for _label, _key in _NAV:
    _active = st.session_state["nav_page"] == _key
    if st.sidebar.button(
        _label,
        key=f"nav_{_key}",
        use_container_width=True,
        type="primary" if _active else "secondary",
    ):
        st.session_state["nav_page"] = _key
        st.rerun()

st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.caption("Outputs → `~/ResearchAnalyserOutput/`")

# ── Sidebar: PaperBanana quick-status ─────────────────────────────────────────
try:
    import paperbanana as _pb_chk  # noqa
    _pb_ver = getattr(_pb_chk, "__version__", "")
    st.sidebar.markdown(
        f'<div style="margin-top:8px">'
        f'<span style="font-size:11px;color:#3fb950">● PaperBanana {_pb_ver} ready</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
except ImportError:
    st.sidebar.markdown(
        '<div style="margin-top:8px">'
        '<span style="font-size:11px;color:#f85149">● PaperBanana not installed</span>'
        '</div>',
        unsafe_allow_html=True,
    )

_page = st.session_state["nav_page"]
if _page == "server":
    show_server_management()
    st.stop()
if _page == "config":
    show_configuration()
    st.stop()

# ── Page: Analyse Paper ───────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
  <p class="hero-title">Research Analyser</p>
  <p class="hero-sub">
    Combine MonkeyOCR extraction · PaperBanana diagrams · LangGraph peer review ·
    STORM Wikipedia reports · Qwen3-TTS narration in one pipeline
  </p>
</div>
""", unsafe_allow_html=True)

# ── Analysis options ──────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown('<p class="sec-label">Analysis Options</p>', unsafe_allow_html=True)
    opt_c1, opt_c2, opt_c3, opt_c4 = st.columns(4)
    generate_diagrams = opt_c1.checkbox("📊  Diagrams",     value=True,  key="opt_diagrams")
    generate_review   = opt_c2.checkbox("🧐  Peer Review",  value=True,  key="opt_review")
    generate_audio    = opt_c3.checkbox("🎙️  Audio (TTS)",   value=_cfg("tts_enabled", False),  key="opt_audio")
    generate_storm    = opt_c4.checkbox("🌪️  STORM Report",  value=_cfg("storm_enabled", False), key="opt_storm")

    if generate_diagrams:
        st.markdown('<div style="height:1px;background:#21262d;margin:12px 0 14px"></div>', unsafe_allow_html=True)
        _dt_options = {"📐 Methodology": "methodology", "🏗️ Architecture": "architecture", "📈 Results": "results"}
        _dt_labels  = list(_dt_options.keys())
        _dt_selected_labels = st.pills(
            "Diagram Types",
            _dt_labels,
            selection_mode="multi",
            default=[_dt_labels[0]],
            key="diagram_type_pills",
        )
        diagram_types = [_dt_options[l] for l in (_dt_selected_labels or [_dt_labels[0]])]
    else:
        diagram_types = ["methodology"]

# ── Input ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="sec-label">Input</p>', unsafe_allow_html=True)

source = None
uploaded_file = None

# Wrap inputs + button in a form so pressing Enter in the URL field
# submits immediately — no need for a separate button click.
with st.form("analysis_form", border=False):
    input_tab1, input_tab2 = st.tabs(["  📎  Upload PDF  ", "  🔗  URL / arXiv / DOI  "])

    with input_tab1:
        uploaded_file = st.file_uploader(
            "Drag and drop a PDF, or click to browse",
            type=["pdf"],
            label_visibility="visible",
        )
        if uploaded_file:
            st.success(f"✓  {uploaded_file.name}  ·  {uploaded_file.size / 1024:.0f} KB")

        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;margin:8px 0'>"
            "<div style='flex:1;height:1px;background:#21262d'></div>"
            "<span style='color:#8b949e;font-size:12px'>or paste file path</span>"
            "<div style='flex:1;height:1px;background:#21262d'></div></div>",
            unsafe_allow_html=True,
        )
        pdf_path_input = st.text_input(
            "PDF file path",
            placeholder="/Users/you/papers/my_paper.pdf",
            label_visibility="collapsed",
            key="pdf_path_input",
            help="Type or paste the full path to a PDF on your Mac — useful inside the app window",
        )
        if pdf_path_input:
            _pp = Path(pdf_path_input.strip())
            if _pp.exists() and _pp.suffix.lower() == ".pdf":
                st.success(f"✓  {_pp.name}  ·  {_pp.stat().st_size / 1024:.0f} KB")
            elif pdf_path_input.strip():
                st.warning("File not found or not a PDF — check the path")

    with input_tab2:
        url_input = st.text_input(
            "Paper URL, arXiv ID, or DOI",
            placeholder="https://arxiv.org/abs/2401.12345  ·  2401.12345  ·  10.1145/...",
            label_visibility="collapsed",
        )
        if url_input:
            source = url_input

    st.markdown("<br>", unsafe_allow_html=True)
    run_clicked = st.form_submit_button(
        "🔬  Analyse Paper", type="primary", use_container_width=True
    )

# ── Run analysis ──────────────────────────────────────────────────────────────
if run_clicked:
    _has_path_input = bool(st.session_state.get("pdf_path_input", "").strip())
    if not source and not uploaded_file and not _has_path_input:
        st.error("Please upload a PDF, enter a paper URL, or paste a PDF file path.")
    else:
        google_api_key = _cfg("google_key",  os.environ.get("GOOGLE_API_KEY", ""))
        openai_api_key = _cfg("openai_key",  os.environ.get("OPENAI_API_KEY", ""))
        tavily_api_key = _cfg("tavily_key",  os.environ.get("TAVILY_API_KEY", ""))
        hf_token       = _cfg("hf_token",    os.environ.get("HF_TOKEN", ""))
        output_dir     = _cfg("output_dir",  _DEFAULT_OUTPUT)
        temp_dir       = _cfg("temp_dir",    _DEFAULT_TEMP)

        for env_key, val in [
            ("GOOGLE_API_KEY", google_api_key),
            ("OPENAI_API_KEY", openai_api_key),
            ("TAVILY_API_KEY", tavily_api_key),
            ("HF_TOKEN",       hf_token),
        ]:
            if val:
                os.environ[env_key] = val

        config = Config.load()
        config.app.output_dir     = output_dir
        config.app.temp_dir       = temp_dir
        config.diagrams.provider         = _cfg("diagram_provider", "gemini")
        config.diagrams.vlm_model        = _cfg("vlm_model", "gemini-2.0-flash")
        config.diagrams.image_model      = _cfg("image_model", "gemini-3-pro-image-preview")
        config.diagrams.max_iterations   = int(_cfg("max_iterations", 3))
        config.diagrams.auto_refine      = _cfg("auto_refine", True)
        config.diagrams.optimize_inputs  = _cfg("optimize_inputs", True)
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
        if google_api_key:  config.google_api_key = google_api_key
        if openai_api_key:  config.openai_api_key = openai_api_key
        if tavily_api_key:  config.tavily_api_key = tavily_api_key

        options = AnalysisOptions(
            generate_diagrams=generate_diagrams,
            generate_review=generate_review,
            generate_audio=generate_audio,
            generate_storm_report=generate_storm,
            diagram_types=diagram_types,
        )

        from research_analyser.analyser import ResearchAnalyser  # deferred
        analyser = ResearchAnalyser(config=config)

        if uploaded_file:
            tmp_path = Path(temp_dir) / "uploads"
            tmp_path.mkdir(parents=True, exist_ok=True)
            file_path = tmp_path / uploaded_file.name
            file_path.write_bytes(uploaded_file.read())
            source = str(file_path)
        elif not source:
            # Path text input fallback (reliable inside pywebview app window)
            _ppi = st.session_state.get("pdf_path_input", "").strip()
            if _ppi:
                _ppi_path = Path(_ppi)
                if _ppi_path.exists() and _ppi_path.suffix.lower() == ".pdf":
                    source = str(_ppi_path)
                else:
                    st.error("PDF path not found or not a PDF file.")
                    st.stop()

        with st.status("Analysing paper…", expanded=True) as _status:
            try:
                def _on_progress(msg: str) -> None:
                    _status.write(msg)

                report = asyncio.run(
                    analyser.analyse(source, options=options, on_progress=_on_progress)
                )
                st.session_state["last_report"] = report
                st.session_state["last_output_dir"] = output_dir
                st.session_state["last_generate_audio"] = generate_audio
                st.session_state["last_generate_storm"] = generate_storm
                _status.update(label="✓  Analysis complete!", state="complete", expanded=False)
            except Exception as e:
                _status.update(label="Analysis failed", state="error")
                st.error(f"Analysis failed: {e}")
                st.exception(e)
                st.stop()

# ── Results ────────────────────────────────────────────────────────────────────
report = st.session_state.get("last_report")
output_dir = st.session_state.get("last_output_dir", _cfg("output_dir", _DEFAULT_OUTPUT))

if report:
    st.markdown('<p class="sec-label">Results</p>', unsafe_allow_html=True)

    # Paper card
    authors_str = ", ".join(report.extracted_content.authors[:4]) if report.extracted_content.authors else ""
    if len(report.extracted_content.authors) > 4:
        authors_str += f" +{len(report.extracted_content.authors) - 4} more"
    st.markdown(
        f'<div class="paper-card">'
        f'  <p class="paper-title">{report.extracted_content.title}</p>'
        f'  <p class="paper-meta">{authors_str}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Stats row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Equations",  len(report.extracted_content.equations))
    m2.metric("Tables",     len(report.extracted_content.tables))
    m3.metric("Figures",    len(report.extracted_content.figures))
    m4.metric("References", len(report.extracted_content.references))

    st.markdown("<br>", unsafe_allow_html=True)

    # Use the options that were active when analysis ran (persisted in session state)
    _gen_audio = st.session_state.get("last_generate_audio", generate_audio)
    _gen_storm = st.session_state.get("last_generate_storm", generate_storm)

    # Result tabs — always add Audio/STORM tabs when they were requested so the
    # user sees an error message rather than the tab silently not appearing.
    tab_labels = ["📝 Summary", "🧐 Peer Review", "∑ Equations", "🎨 Diagrams", "⬇ Downloads"]
    if _gen_audio:
        tab_labels.append("🎙️ Audio")
    if _gen_storm:
        tab_labels.append("🌪️ STORM")

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # ── Summary tab ───────────────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        if report.summary:
            st.markdown(
                f'<p style="font-size:15px;color:#c9d1d9;line-height:1.6">'
                f'{report.summary.one_sentence}</p>',
                unsafe_allow_html=True,
            )
            s1, s2, s3 = st.columns(3, gap="medium")
            with s1:
                with st.expander("📖 Abstract", expanded=True):
                    st.write(report.summary.abstract_summary)
            with s2:
                with st.expander("⚙️ Methodology", expanded=True):
                    st.write(report.summary.methodology_summary)
            with s3:
                with st.expander("📊 Results", expanded=True):
                    st.write(report.summary.results_summary)

        if report.key_points:
            st.markdown('<p class="sec-label">Key Findings</p>', unsafe_allow_html=True)
            for kp in report.key_points:
                icon = "🔴" if kp.importance == "high" else "🟡"
                with st.expander(f"{icon}  {kp.point}"):
                    st.markdown(f"**Evidence:** {kp.evidence}")
                    st.markdown(f'<span class="paper-chip">{kp.section}</span>', unsafe_allow_html=True)

    # ── Peer Review tab ───────────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        if report.review:
            from research_analyser.reviewer import interpret_score  # deferred
            score    = report.review.overall_score
            decision = interpret_score(score)

            sc_col, dims_col = st.columns([1, 3], gap="large")

            with sc_col:
                st.markdown(
                    f'<div class="score-block">'
                    f'  <span class="score-num">{score:.1f}</span>'
                    f'  <span class="score-denom">out of 10</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(_decision_pill(decision, score), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                st.metric("Confidence", f"{report.review.confidence:.0f} / 5")

            with dims_col:
                st.markdown('<p class="sec-label">Dimensional Scores</p>', unsafe_allow_html=True)
                bars_html = ""
                for dim_name, dim in report.review.dimensions.items():
                    bars_html += _dimbar(dim.name, dim.score)
                st.markdown(bars_html, unsafe_allow_html=True)

            sw1, sw2 = st.columns(2, gap="medium")
            with sw1:
                st.markdown('<p class="sec-label">Strengths</p>', unsafe_allow_html=True)
                sw_html = ""
                for s in report.review.strengths:
                    sw_html += f'<div class="sw-row"><span class="sw-icon">✅</span>{s}</div>'
                st.markdown(sw_html, unsafe_allow_html=True)
            with sw2:
                st.markdown('<p class="sec-label">Weaknesses</p>', unsafe_allow_html=True)
                sw_html = ""
                for w in report.review.weaknesses:
                    sw_html += f'<div class="sw-row"><span class="sw-icon">⚠️</span>{w}</div>'
                st.markdown(sw_html, unsafe_allow_html=True)
        else:
            st.info("Peer review was not requested for this run.")

    # ── Equations tab ─────────────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        display_eqs = [e for e in report.extracted_content.equations if not e.is_inline]
        if display_eqs:
            for eq in display_eqs[:10]:
                with st.expander(f"**{eq.label or eq.id}**  ·  {eq.section}"):
                    st.latex(eq.latex)
                    if eq.description:
                        st.caption(eq.description)
        else:
            st.info("No display equations found.")

    # ── Diagrams tab ──────────────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        if report.diagrams:
            # Banner if any diagram fell back to matplotlib
            _fallbacks = [d for d in report.diagrams if getattr(d, "is_fallback", False)]
            if _fallbacks:
                st.warning(
                    f"**{len(_fallbacks)} of {len(report.diagrams)} diagram(s) used the matplotlib fallback** "
                    "— PaperBanana failed. See the error details below each diagram.",
                    icon="⚠️",
                )

            cols = st.columns(min(len(report.diagrams), 2), gap="medium")
            for i, diagram in enumerate(report.diagrams):
                with cols[i % 2]:
                    _is_fb = getattr(diagram, "is_fallback", False)
                    _badge = (
                        '<span class="badge badge-gray">matplotlib fallback</span>'
                        if _is_fb else
                        '<span class="badge badge-green">PaperBanana</span>'
                    )
                    st.markdown(
                        f'<span class="paper-chip">{diagram.diagram_type.title()}</span> {_badge}',
                        unsafe_allow_html=True,
                    )
                    if Path(diagram.image_path).exists():
                        st.image(diagram.image_path, caption=diagram.caption, use_container_width=True)
                    else:
                        st.info(f"Saved: `{diagram.image_path}`")

                    # Error details when PaperBanana failed
                    if _is_fb and getattr(diagram, "error", ""):
                        with st.expander("PaperBanana error details"):
                            st.code(diagram.error, language=None)
                            if diagram.source_context:
                                st.caption("Context sent to PaperBanana:")
                                st.text(diagram.source_context[:800])
        else:
            st.info("No diagrams were generated for this run.")

    # ── Downloads tab ─────────────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        d1, d2 = st.columns(2, gap="medium")
        report_md = report.to_markdown()
        with d1:
            st.download_button(
                "⬇  Full Report (Markdown)",
                report_md,
                file_name="analysis_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with d2:
            import datetime as _dt
            def _json_serial(obj):
                if isinstance(obj, (_dt.datetime, _dt.date)):
                    return obj.isoformat()
                raise TypeError(f"Type {type(obj).__name__} not serializable")
            report_json = json.dumps(report.to_json(), indent=2, ensure_ascii=False, default=_json_serial)
            st.download_button(
                "⬇  Report (JSON)",
                report_json,
                file_name="analysis_report.json",
                mime="application/json",
                use_container_width=True,
            )
        # Optional audio + STORM downloads if they were generated
        audio_file = Path(output_dir) / "analysis_audio.wav"
        storm_file = Path(output_dir) / "storm_report.md"
        if _gen_audio and audio_file.exists():
            st.markdown("---")
            with open(audio_file, "rb") as af:
                st.download_button(
                    "⬇  Audio Narration (WAV)",
                    af.read(),
                    file_name="analysis_audio.wav",
                    mime="audio/wav",
                    use_container_width=True,
                )
        if _gen_storm and storm_file.exists():
            st.markdown("---")
            st.download_button(
                "⬇  STORM Report (Markdown)",
                storm_file.read_text(encoding="utf-8"),
                file_name="storm_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        st.success(f"All outputs saved to: `{output_dir}`")

    # ── Audio tab ─────────────────────────────────────────────────────────────
    if _gen_audio and tab_idx < len(tabs):
        with tabs[tab_idx]:
            tab_idx += 1
            audio_file = Path(output_dir) / "analysis_audio.wav"
            if audio_file.exists():
                st.audio(str(audio_file), format="audio/wav")
                with open(audio_file, "rb") as af:
                    st.download_button(
                        "⬇  Download WAV",
                        af.read(),
                        file_name="analysis_audio.wav",
                        mime="audio/wav",
                        use_container_width=True,
                    )
            else:
                st.warning(
                    "Audio narration was not generated. Common causes:\n"
                    "- **HuggingFace Token** not set in Configuration\n"
                    "- `soundfile` / `transformers` package missing\n"
                    "- TTS model download failed\n\n"
                    "Check the app logs for details."
                )

    # ── STORM tab ─────────────────────────────────────────────────────────────
    if _gen_storm and tab_idx < len(tabs):
        with tabs[tab_idx]:
            tab_idx += 1
            if report.storm_report:
                st.markdown(report.storm_report)
                st.download_button(
                    "⬇  Download STORM Report (Markdown)",
                    report.storm_report,
                    file_name="storm_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            else:
                st.warning(
                    "STORM report was not generated. Common causes:\n"
                    "- **OpenAI API Key** not set in Configuration\n"
                    "- `knowledge-storm` or `dspy-ai` package missing\n\n"
                    "Install with: `pip install knowledge-storm`\n\n"
                    "Check the app logs for details."
                )


# ── PaperReview.ai Comparison ─────────────────────────────────────────────────
st.divider()
st.markdown('<p class="sec-label">External Comparison</p>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown(
        '<div class="cfg-hdr"><div class="cfg-icon cfg-icon-diag">📊</div>'
        'PaperReview.ai Score Comparison</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Upload a review JSON from [PaperReview.ai](https://paperreview.ai) to compare scores. "
        'Expected format: `{"overall_score": 6.9, "soundness": 3.1, "presentation": 3.0, "contribution": 3.2, "confidence": 3.5}`'
    )

    ext_file = st.file_uploader(
        "Upload external review (JSON)",
        type=["json"],
        key="external_review",
        label_visibility="collapsed",
    )

if ext_file is not None:
    try:
        from research_analyser.comparison import ReviewSnapshot, build_comparison_markdown, parse_local_review
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

        st.markdown('<p class="sec-label">External Review Scores</p>', unsafe_allow_html=True)
        ec = st.columns(5)
        ec[0].metric("Overall",      f"{external.overall_score:.1f}/10"  if external.overall_score  else "—")
        ec[1].metric("Soundness",    f"{external.soundness:.1f}/4"        if external.soundness       else "—")
        ec[2].metric("Presentation", f"{external.presentation:.1f}/4"     if external.presentation    else "—")
        ec[3].metric("Contribution", f"{external.contribution:.1f}/4"     if external.contribution    else "—")
        ec[4].metric("Confidence",   f"{external.confidence:.1f}/5"       if external.confidence      else "—")

        if external.overall_score is not None:
            st.markdown(
                _decision_pill(interpret_score(external.overall_score), external.overall_score),
                unsafe_allow_html=True,
            )

        cur_report  = st.session_state.get("last_report")
        cur_out_dir = st.session_state.get("last_output_dir", _cfg("output_dir", _DEFAULT_OUTPUT))
        if cur_report and cur_report.review:
            review = cur_report.review
            dims   = review.dimensions or {}
            local  = ReviewSnapshot(
                source="local",
                overall_score=review.overall_score,
                soundness=dims.get("soundness").score if dims.get("soundness") else None,
                presentation=dims.get("presentation").score if dims.get("presentation") else None,
                contribution=dims.get("contribution").score if dims.get("contribution") else None,
                confidence=review.confidence,
            )
        else:
            local = parse_local_review(Path(cur_out_dir))

        st.markdown('<p class="sec-label">Comparison</p>', unsafe_allow_html=True)
        comparison_md = build_comparison_markdown(local, external)
        st.markdown(comparison_md)
        st.download_button(
            "⬇  Download Comparison (Markdown)",
            comparison_md,
            file_name="review_comparison.md",
            mime="text/markdown",
        )
    except json.JSONDecodeError:
        st.error("Invalid JSON — please upload a valid review JSON file.")
    except Exception as e:
        st.error(f"Comparison failed: {e}")
        st.exception(e)

# ── Late CSS override (injected last so it beats Streamlit component CSS) ──────
st.markdown("""
<style>
:root { --text-color: #ffffff !important; }
.stApp, .stApp * { color: #ffffff; }
/* Re-apply intentionally dim elements */
[data-testid="stMetricLabel"]            { color: #e6edf3 !important; }
[data-testid="stSidebar"] .stCaption p  { color: #8b949e !important; }
.svc-url                                { color: #8b949e !important; }
.score-denom                            { color: #8b949e !important; }
[data-testid="stPills"] button          { color: #8b949e !important; }
[data-testid="stPills"] button[aria-selected="true"],
[data-testid="stPills"] button[aria-pressed="true"]  { color: #58a6ff !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"] { color: #58a6ff !important; }
.hero-title { color: transparent !important; }
.sec-label  { color: #58a6ff !important; }
.badge-green  { color: #3fb950 !important; }
.badge-blue   { color: #58a6ff !important; }
.badge-purple { color: #bc8cff !important; }
.badge-gray   { color: #8b949e !important; }
.dot-green { color: #3fb950 !important; }
.dot-red   { color: #f85149 !important; }
.dimbar-val  { color: #58a6ff !important; }
.score-num   { color: #58a6ff !important; }
.paper-chip  { color: #58a6ff !important; }
.paper-meta  { color: #c9d1d9 !important; }
.hero-sub    { color: #c9d1d9 !important; }
.stTabs [aria-selected="true"] { color: #58a6ff !important; }
</style>
""", unsafe_allow_html=True)
