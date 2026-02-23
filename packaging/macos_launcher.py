"""macOS app launcher — lightweight bundle + first-launch dependency installer.

Architecture
────────────
The PyInstaller bundle contains ONLY:
  • Python interpreter + stdlib
  • pywebview  (for the native macOS window)
  • app source files (app.py, config.yaml, research_analyser/, monkeyocr.py)

On first launch the launcher:
  1. Shows a native webview setup screen.
  2. Finds a suitable system Python 3.10+ (Homebrew / pyenv / Xcode CLT).
  3. Creates ~/.researchanalyser/venv and pip-installs all heavy deps
     (torch, streamlit, langchain, …) into it.
  4. Writes a completion marker so subsequent launches skip setup.
  5. Starts Streamlit as a subprocess from the companion venv.
  6. Navigates the webview window to the running Streamlit server.

Subsequent launches skip straight to step 5.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── Stable paths ──────────────────────────────────────────────────────────────
_APP_SUPPORT  = Path.home() / ".researchanalyser"
_VENV         = _APP_SUPPORT / "venv"
# Bump the suffix to force a reinstall after major dependency changes.
_SETUP_MARKER = _APP_SUPPORT / ".setup_v1_complete"
_OUTPUT_DIR   = Path.home() / "ResearchAnalyserOutput"

# ── Logging ───────────────────────────────────────────────────────────────────
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_OUTPUT_DIR / "launcher.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def resource_path(relative: str) -> Path:
    """Resolve a resource path for both frozen and dev modes."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative


def _find_free_port(start: int = 8502, end: int = 8600) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    return start


def _clean_env() -> dict:
    """Return os.environ without DYLD_* keys.

    PyInstaller sets DYLD_LIBRARY_PATH / DYLD_FRAMEWORK_PATH to point at
    bundled libraries.  When we spawn an external Python binary those vars
    cause it to load the WRONG dylibs (from the .app bundle) and crash or
    report the wrong version.  Strip them so subprocesses get a clean env.
    """
    return {k: v for k, v in os.environ.items()
            if not k.startswith("DYLD_")}


def _find_python() -> str | None:
    """Return the path to a Python 3.10+ interpreter.

    macOS apps launched from Finder have a stripped PATH (/usr/bin:/bin only)
    so shutil.which() can't find Homebrew Python directly.  PyInstaller also
    sets DYLD_LIBRARY_PATH which breaks external Python subprocesses unless
    stripped.

    Search order:
    1. Absolute paths at all known Homebrew/installer locations (fast).
    2. Login shell (zsh -l) — loads ~/.zprofile so non-standard installs
       (pyenv, conda, custom prefix) are found via the user's PATH.
    """
    _env = _clean_env()

    def _verify(path: str) -> bool:
        """Return True if path is a Python 3.10+ executable."""
        try:
            r = subprocess.run(
                [path, "-c",
                 "import sys; v=sys.version_info; print(v.major*100+v.minor)"],
                capture_output=True, text=True, timeout=10, env=_env,
            )
            log.debug("_verify %s → rc=%s out=%r", path, r.returncode,
                      r.stdout.strip())
            return r.returncode == 0 and int(r.stdout.strip()) >= 310
        except Exception as exc:
            log.debug("_verify %s raised: %s", path, exc)
            return False

    # ── 1. Absolute paths (fastest, covers 99% of macOS installs) ────────────
    candidates = [
        "/opt/homebrew/bin/python3.13",
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3.11",
        "/opt/homebrew/bin/python3.10",
        "/opt/homebrew/opt/python@3.13/bin/python3.13",
        "/opt/homebrew/opt/python@3.12/bin/python3.12",
        "/opt/homebrew/opt/python@3.11/bin/python3.11",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3.13",
        "/usr/local/bin/python3.12",
        "/usr/local/bin/python3.11",
        "/usr/local/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
        "/usr/bin/python3",
    ]
    for path in candidates:
        log.debug("Checking absolute path: %s (exists=%s)", path,
                  os.path.isfile(path))
        if os.path.isfile(path) and _verify(path):
            log.info("Found Python at absolute path: %s", path)
            return path

    # ── 2. Login shell fallback (pyenv / conda / custom prefix) ──────────────
    for shell in ("/bin/zsh", "/bin/bash"):
        if not os.path.isfile(shell):
            continue
        for py_name in ("python3.13", "python3.12", "python3.11", "python3.10",
                        "python3"):
            try:
                r = subprocess.run(
                    [shell, "-l", "-c", f"which {py_name}"],
                    capture_output=True, text=True, timeout=20, env=_env,
                )
                log.debug("shell which %s → rc=%s out=%r err=%r",
                          py_name, r.returncode, r.stdout.strip(),
                          r.stderr.strip()[:100])
                path = r.stdout.strip().splitlines()[0] if r.returncode == 0 else ""
                if path and os.path.isfile(path) and _verify(path):
                    log.info("Found Python via %s login shell: %s", shell, path)
                    return path
            except Exception as exc:
                log.debug("shell search %s/%s raised: %s", shell, py_name, exc)
                continue

    log.error("No Python 3.10+ found — checked %d absolute paths + login shell",
              len(candidates))
    return None


def _wait_for_server(port: int, timeout: int = 120) -> bool:
    """Poll until Streamlit's health endpoint responds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{port}/_stcore/health", timeout=1
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


# ── Packages installed into the companion venv ────────────────────────────────
# pip/wheel first so upgrades propagate; torch last (biggest download).
_PACKAGES = [
    ("pip", ["install", "--upgrade", "pip"]),
    ("wheel", ["install", "wheel"]),
    ("python-dotenv", ["install", "python-dotenv>=1.0.0"]),
    ("pydantic", ["install", "pydantic>=2.0"]),
    ("pydantic-settings", ["install", "pydantic-settings>=2.0"]),
    ("pyyaml", ["install", "pyyaml>=6.0"]),
    ("aiohttp", ["install", "aiohttp>=3.9"]),
    ("aiofiles", ["install", "aiofiles>=23.0"]),
    ("httpx", ["install", "httpx>=0.25"]),
    ("rich", ["install", "rich>=13.0"]),
    ("click", ["install", "click>=8.1"]),
    ("tqdm", ["install", "tqdm>=4.65"]),
    ("Pillow", ["install", "Pillow>=10.0"]),
    ("PyMuPDF", ["install", "PyMuPDF>=1.23"]),
    ("streamlit", ["install", "streamlit>=1.30"]),
    ("altair", ["install", "altair>=5"]),
    ("fastapi", ["install", "fastapi>=0.100"]),
    ("uvicorn", ["install", "uvicorn[standard]>=0.24"]),
    ("python-multipart", ["install", "python-multipart>=0.0.6"]),
    ("scikit-learn", ["install", "scikit-learn>=1.3"]),
    ("langchain-core", ["install", "langchain-core>=0.2"]),
    ("langchain", ["install", "langchain>=0.2"]),
    ("langchain-openai", ["install", "langchain-openai>=0.1"]),
    ("langchain-community", ["install", "langchain-community>=0.2"]),
    ("langgraph", ["install", "langgraph>=0.2"]),
    ("tavily-python", ["install", "tavily-python>=0.3"]),
    ("knowledge-storm", ["install", "knowledge-storm>=1.0.0"]),
    ("torch", ["install", "torch>=2.1", "--index-url",
               "https://download.pytorch.org/whl/cpu"]),
    ("torchvision", ["install", "torchvision>=0.16", "--index-url",
                     "https://download.pytorch.org/whl/cpu"]),
]


# ── Setup page HTML ───────────────────────────────────────────────────────────
_SETUP_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;
     font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     display:flex;align-items:center;justify-content:center;
     min-height:100vh;padding:40px}
.card{max-width:540px;width:100%;background:#161b22;
      border:1px solid #21262d;border-radius:16px;padding:44px}
.icon{font-size:48px;margin-bottom:18px}
h1{font-size:22px;font-weight:800;color:#f0f6fc;margin-bottom:10px}
.sub{font-size:14px;color:#8b949e;line-height:1.65;margin-bottom:32px}
.sub code{color:#c9d1d9;background:#21262d;padding:1px 6px;border-radius:4px}
.track{height:6px;background:#21262d;border-radius:99px;
       overflow:hidden;margin-bottom:12px}
.fill{height:100%;width:0%;
      background:linear-gradient(90deg,#388bfd,#8957e5);
      border-radius:99px;transition:width .4s ease}
.row{display:flex;justify-content:space-between;align-items:center;
     font-size:12px;color:#8b949e;min-height:18px}
.pkg{font-size:12px;color:#58a6ff;font-family:monospace;min-height:18px;
     margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.done{display:none;margin-top:24px;color:#3fb950;font-weight:600;font-size:14px}
.err{display:none;margin-top:24px;color:#f85149;font-size:13px;line-height:1.5}
</style></head><body>
<div class="card">
  <div class="icon">🔬</div>
  <h1>Setting up Research Analyser</h1>
  <p class="sub">
    Installing dependencies into <code>~/.researchanalyser/venv</code>.<br>
    This only runs once and takes a few minutes — coffee time ☕
  </p>
  <div class="track"><div class="fill" id="fill"></div></div>
  <div class="row">
    <span id="status">Preparing…</span>
    <span id="pct">0%</span>
  </div>
  <div class="pkg" id="pkg"></div>
  <div class="done" id="done">✓ Setup complete — launching app…</div>
  <div class="err" id="err"></div>
</div>
<script>
function updateProgress(done,total,pkg){
  var p=total>0?Math.round(done/total*100):0;
  document.getElementById('fill').style.width=p+'%';
  document.getElementById('pct').textContent=p+'%';
  document.getElementById('status').textContent=done+' / '+total+' packages';
  document.getElementById('pkg').textContent=pkg?'Installing: '+pkg:'';
}
function showDone(){
  document.getElementById('done').style.display='block';
  document.getElementById('pkg').textContent='';
  document.getElementById('fill').style.width='100%';
  document.getElementById('pct').textContent='100%';
  document.getElementById('status').textContent='All packages installed.';
}
function showError(msg){
  var el=document.getElementById('err');
  el.style.display='block';
  el.textContent='Error: '+msg;
  document.getElementById('pkg').textContent='';
}
</script></body></html>"""


# ── Core logic ────────────────────────────────────────────────────────────────

def _launch_streamlit(port: int, app_script: Path, config_file: Path) -> subprocess.Popen | None:
    """Start Streamlit from the companion venv; return the process or None."""
    python = _VENV / "bin" / "python"
    if not python.exists():
        log.error("Companion venv Python not found: %s", python)
        return None

    env = {
        **os.environ,
        # Allow research_analyser package to be imported from the bundle
        "PYTHONPATH": str(app_script.parent),
        "RESEARCH_ANALYSER_OUTPUT_DIR": str(_OUTPUT_DIR),
        "RESEARCH_ANALYSER_APP__OUTPUT_DIR": str(_OUTPUT_DIR),
        "RESEARCH_ANALYSER_APP__TEMP_DIR": str(_OUTPUT_DIR / "tmp"),
        "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false",
    }
    if config_file.exists():
        env["RESEARCH_ANALYSER_CONFIG"] = str(config_file)

    cmd = [
        str(python), "-m", "streamlit", "run", str(app_script),
        "--server.headless", "true",
        "--server.port", str(port),
        "--server.address", "localhost",
        "--global.developmentMode", "false",
        "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "none",
    ]
    log.info("Starting Streamlit subprocess …")
    return subprocess.Popen(cmd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _do_setup(window, port: int, app_script: Path, config_file: Path) -> None:
    """Run in a background thread: install deps, then launch Streamlit."""
    python = _find_python()
    if not python:
        msg = ("Python 3.10+ not found. "
               "Install it from python.org or via Homebrew: brew install python@3.12")
        log.error(msg)
        window.evaluate_js(f'showError("{msg}")')
        return

    log.info("Creating companion venv at %s using %s", _VENV, python)
    window.evaluate_js('updateProgress(0,0,"Creating virtual environment…")')
    try:
        subprocess.run([python, "-m", "venv", str(_VENV)], check=True,
                       capture_output=True)
    except subprocess.CalledProcessError as exc:
        msg = f"Failed to create venv: {exc.stderr.decode()[:200]}"
        log.error(msg)
        window.evaluate_js(f'showError("{msg}")')
        return

    pip = str(_VENV / "bin" / "pip")
    total = len(_PACKAGES)
    for i, (label, args) in enumerate(_PACKAGES):
        window.evaluate_js(f'updateProgress({i},{total},"{label}")')
        log.info("[%d/%d] Installing %s …", i + 1, total, label)
        result = subprocess.run([pip] + args, capture_output=True, text=True)
        if result.returncode != 0:
            log.warning("pip %s failed (non-fatal):\n%s", label,
                        result.stderr[-400:])

    _SETUP_MARKER.touch()
    log.info("Setup complete — marker written")
    window.evaluate_js('showDone()')
    time.sleep(2)

    _finish_launch(window, port, app_script, config_file)


def _finish_launch(window, port: int, app_script: Path, config_file: Path) -> None:
    """Start Streamlit and navigate the existing window to it."""
    proc = _launch_streamlit(port, app_script, config_file)
    if proc is None:
        window.evaluate_js('showError("Could not start Streamlit.")')
        return

    log.info("Waiting for Streamlit on port %d …", port)
    if not _wait_for_server(port):
        log.error("Streamlit did not respond within 120 s")
        window.evaluate_js('showError("Streamlit failed to start — check launcher.log")')
        proc.terminate()
        return

    log.info("Streamlit ready — loading UI")
    window.title = "Research Analyser"
    window.load_url(f"http://localhost:{port}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    log.info("Launcher started — MEIPASS=%s", getattr(sys, "_MEIPASS", None))

    app_script  = resource_path("app.py")
    config_file = resource_path("config.yaml")

    _APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    (_OUTPUT_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    if not app_script.exists():
        log.error("app.py not found at %s", app_script)
        return 1

    port = _find_free_port()
    setup_needed = not _SETUP_MARKER.exists()

    import webview  # noqa: PLC0415  (deferred — not bundled on next builds)

    if setup_needed:
        log.info("First-time setup required")
        window = webview.create_window(
            "Research Analyser — First-time Setup",
            html=_SETUP_HTML,
            width=620, height=520,
            resizable=False,
        )
        webview.start(
            lambda: _do_setup(window, port, app_script, config_file),
        )
    else:
        log.info("Setup already done — launching normally")
        loading_html = (
            "<body style='background:#0d1117;color:#e6edf3;"
            "font-family:-apple-system,sans-serif;display:flex;"
            "align-items:center;justify-content:center;height:100vh;"
            "font-size:18px;gap:12px'>🔬 Starting Research Analyser…</body>"
        )
        window = webview.create_window(
            "Research Analyser",
            html=loading_html,
            width=1440, height=900,
            min_size=(960, 640),
        )
        webview.start(
            lambda: _finish_launch(window, port, app_script, config_file),
        )

    log.info("Webview closed — exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
