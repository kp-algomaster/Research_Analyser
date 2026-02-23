"""macOS app launcher for bundled Streamlit Research Analyser."""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# ── Log to file (no console in windowed .app) ─────────────────────────────────
_log_dir = Path.home() / "ResearchAnalyserOutput"
_log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_log_dir / "launcher.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def resource_path(relative: str) -> Path:
    """Resolve resource path for both dev and frozen modes."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative


def _find_free_port(start: int = 8502, end: int = 8600) -> int:
    """Return the first TCP port in [start, end) that is not in use."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    return start  # fallback


def _start_streamlit(app_script: Path, port: int) -> None:
    """Run the Streamlit server in headless mode.

    Streamlit calls signal.signal() during startup, which raises ValueError
    when called from a non-main thread.  We patch signal.signal in this thread
    to silently swallow that error so the server keeps running.
    """
    _orig_signal = signal.signal

    def _thread_safe_signal(signum, handler):
        try:
            return _orig_signal(signum, handler)
        except ValueError:
            pass  # signal.signal() is a no-op outside the main thread

    signal.signal = _thread_safe_signal  # type: ignore[assignment]

    try:
        from streamlit.web import cli as stcli

        sys.argv = [
            "streamlit",
            "run",
            str(app_script),
            "--server.headless",
            "true",
            "--server.port",
            str(port),
            "--server.address",
            "localhost",
            "--global.developmentMode",
            "false",
            "--browser.gatherUsageStats",
            "false",
            "--server.fileWatcherType",
            "none",  # disable file watcher (no inotify needed in bundle)
        ]
        log.info("Starting Streamlit on port %d …", port)
        stcli.main()
    except Exception:
        log.exception("Streamlit thread crashed")
    finally:
        signal.signal = _orig_signal  # type: ignore[assignment]


def _wait_for_server(port: int, timeout: int = 90) -> bool:
    """Poll until Streamlit's health endpoint responds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{port}/_stcore/health", timeout=1
            ) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    log.info("Launcher started (sys._MEIPASS=%s)", getattr(sys, "_MEIPASS", None))

    app_script = resource_path("app.py")
    config_file = resource_path("config.yaml")

    if not app_script.exists():
        log.error("App script not found: %s", app_script)
        return 1

    output_dir = Path.home() / "ResearchAnalyserOutput"
    tmp_dir = Path.home() / "ResearchAnalyserOutput" / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if config_file.exists():
        os.environ.setdefault("RESEARCH_ANALYSER_CONFIG", str(config_file))
    # Top-level convenience var read directly by app.py widget default
    os.environ.setdefault("RESEARCH_ANALYSER_OUTPUT_DIR", str(output_dir))
    # Nested pydantic-settings vars so Config.load() picks up writable paths
    os.environ.setdefault("RESEARCH_ANALYSER_APP__OUTPUT_DIR", str(output_dir))
    os.environ.setdefault("RESEARCH_ANALYSER_APP__TEMP_DIR", str(tmp_dir))
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")

    port = _find_free_port()
    log.info("Using port %d", port)

    # Start Streamlit in a daemon thread — headless, no browser
    t = threading.Thread(
        target=_start_streamlit, args=(app_script, port), daemon=True
    )
    t.start()

    # Wait for the server to accept connections before opening the window
    log.info("Waiting for Streamlit to become healthy …")
    if not _wait_for_server(port):
        log.error("Streamlit server did not start within 90 s")
        return 1

    log.info("Streamlit healthy — opening webview window")

    # Show the UI in a native macOS webview window (no external browser)
    import webview

    webview.create_window(
        "Research Analyser",
        f"http://localhost:{port}",
        width=1440,
        height=900,
        min_size=(960, 640),
    )
    webview.start()
    log.info("Webview closed — exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
