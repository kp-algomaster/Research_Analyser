"""macOS app launcher for bundled Streamlit Research Analyser."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resolve resource path for both dev and frozen modes."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative


def main() -> int:
    app_script = resource_path("app.py")
    config_file = resource_path("config.yaml")

    if not app_script.exists():
        print(f"App script not found: {app_script}")
        return 1

    output_dir = Path.home() / "ResearchAnalyserOutput"
    output_dir.mkdir(parents=True, exist_ok=True)

    if config_file.exists():
        os.environ.setdefault("RESEARCH_ANALYSER_CONFIG", str(config_file))
    os.environ.setdefault("RESEARCH_ANALYSER_OUTPUT_DIR", str(output_dir))
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_SERVER_PORT", "8502")
    os.environ.setdefault("STREAMLIT_BROWSER_SERVER_PORT", "8502")
    os.environ.setdefault("STREAMLIT_BROWSER_SERVER_ADDRESS", "localhost")

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_script),
        "--server.headless",
        "false",
        "--server.port",
        "8502",
        "--server.address",
        "localhost",
        "--browser.serverPort",
        "8502",
        "--browser.serverAddress",
        "localhost",
        "--global.developmentMode",
        "false",
        "--browser.gatherUsageStats",
        "false",
    ]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
