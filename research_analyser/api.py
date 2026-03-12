"""FastAPI server for Research Analyser."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

# Load .env BEFORE anything reads os.getenv()
from dotenv import load_dotenv
load_dotenv()

# Ensure cairo native library is discoverable (macOS Homebrew)
import os as _os
_brew_lib = "/opt/homebrew/lib"
if _os.path.isdir(_brew_lib):
    _os.environ.setdefault(
        "DYLD_FALLBACK_LIBRARY_PATH",
        _brew_lib + ":" + _os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", ""),
    )

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

try:
    from sse_starlette.sse import EventSourceResponse
    _SSE_AVAILABLE = True
except ImportError:
    _SSE_AVAILABLE = False

from research_analyser.analyser import ResearchAnalyser
from research_analyser.config import Config
from research_analyser.models import AnalysisOptions

logger = logging.getLogger(__name__)


def _json_default(obj):
    """Handle non-serializable types for json.dumps."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


app = FastAPI(
    title="Research Analyser API",
    description="AI-powered research paper analysis",
    version="0.1.0",
)

# In-memory job store (replace with Redis/DB for production)
jobs: dict[str, dict] = {}
config = Config.load()
analyser = ResearchAnalyser(config=config)


class AnalyseRequest(BaseModel):
    source: str
    source_type: Optional[str] = None
    venue: Optional[str] = None
    generate_diagrams: bool = True
    generate_review: bool = True
    generate_audio: bool = False
    diagram_types: list[str] = ["methodology"]
    diagram_engine: str = "paperbanana"  # "paperbanana" or "beautiful_mermaid"


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    report: Optional[dict] = None
    error: Optional[str] = None


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/api/v1/analyse", response_model=JobResponse)
async def analyse_paper(
    file: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None),
    venue: Optional[str] = Form(None),
    generate_diagrams: bool = Form(True),
    generate_review: bool = Form(True),
    generate_audio: bool = Form(False),
):
    """Submit a paper for analysis. Upload a PDF file or provide a URL/arXiv ID."""
    job_id = str(uuid.uuid4())

    if file:
        # Save uploaded file
        upload_dir = Path(config.app.temp_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{job_id}_{file.filename}"
        content = await file.read()
        file_path.write_bytes(content)
        paper_source = str(file_path)
    elif source:
        paper_source = source
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or source URL")

    jobs[job_id] = {"status": "queued", "report": None, "error": None}

    options = AnalysisOptions(
        generate_diagrams=generate_diagrams,
        generate_review=generate_review,
        generate_audio=generate_audio,
    )

    # Run analysis in background
    asyncio.create_task(_run_analysis(job_id, paper_source, options))

    return JobResponse(job_id=job_id, status="queued", message="Analysis started")


async def _run_analysis(job_id: str, source: str, options: AnalysisOptions):
    """Run analysis as a background task."""
    jobs[job_id]["status"] = "processing"
    try:
        report = await analyser.analyse(source, options=options)
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["report"] = report.to_json()
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.get("/api/v1/analyse/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get analysis job status and results."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        report=job.get("report"),
        error=job.get("error"),
    )


@app.post("/api/v1/extract")
async def extract_only(
    file: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None),
):
    """Extract content only (no review or diagrams)."""
    options = AnalysisOptions(
        generate_diagrams=False,
        generate_review=False,
    )

    if file:
        upload_dir = Path(config.app.temp_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / file.filename
        content = await file.read()
        file_path.write_bytes(content)
        paper_source = str(file_path)
    elif source:
        paper_source = source
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or source URL")

    report = await analyser.analyse(paper_source, options=options)
    return report.to_json()


# ---------------------------------------------------------------------------
# VS Code Extension-compatible endpoints
# ---------------------------------------------------------------------------

# Shared storage for the last completed report (in-memory, single-user)
_last_report: Optional[dict] = None


class VSCodeAnalyseRequest(BaseModel):
    source: str
    options: Optional[dict] = None


@app.get("/health")
async def health():
    """VS Code extension health check."""
    return {"status": "ok"}


@app.get("/report/latest")
async def get_latest_report():
    """Return the most recent analysis report (for VS Code extension auto-load)."""
    if _last_report is None:
        raise HTTPException(status_code=404, detail="No report available")
    return _last_report


@app.post("/analyse")
async def analyse_blocking(req: VSCodeAnalyseRequest):
    """Run analysis and return the full report (blocking, 300 s budget)."""
    global _last_report
    options = AnalysisOptions(
        generate_diagrams=req.options.get("generate_diagrams", True) if req.options else True,
        generate_review=req.options.get("generate_review", True) if req.options else True,
        generate_audio=req.options.get("generate_audio", False) if req.options else False,
        diagram_engine=req.options.get("diagram_engine", "paperbanana") if req.options else "paperbanana",
    )
    try:
        report = await analyser.analyse(req.source, options=options)
        _last_report = report.to_json()
        return _last_report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/analyse/stream")
async def analyse_stream(req: VSCodeAnalyseRequest):
    """Run analysis with Server-Sent Events progress stream (VS Code extension)."""
    if not _SSE_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="SSE streaming not available. Install sse-starlette: pip install sse-starlette",
        )

    global _last_report
    options = AnalysisOptions(
        generate_diagrams=req.options.get("generate_diagrams", True) if req.options else True,
        generate_review=req.options.get("generate_review", True) if req.options else True,
        generate_audio=req.options.get("generate_audio", False) if req.options else False,
        diagram_engine=req.options.get("diagram_engine", "paperbanana") if req.options else "paperbanana",
    )

    async def generate() -> AsyncGenerator[dict, None]:
        global _last_report
        try:
            # Emit initial progress
            yield {
                "event": "progress",
                "data": json.dumps({"pct": 5, "message": "Starting analysis…"}),
            }

            # Run analysis (no streaming inside analyser yet — emit milestones)
            yield {
                "event": "progress",
                "data": json.dumps({"pct": 10, "message": "Downloading / loading paper…"}),
            }

            report = await analyser.analyse(req.source, options=options)
            _last_report = report.to_json()

            yield {
                "event": "progress",
                "data": json.dumps({"pct": 95, "message": "Finalising report…"}),
            }

            yield {"event": "complete", "data": json.dumps(_last_report, default=_json_default)}
        except Exception as exc:
            logger.error("SSE analysis failed: %s", exc)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(generate())


@app.get("/equations")
async def get_equations():
    """Return equations from the latest report (without loading the full report)."""
    if _last_report is None:
        raise HTTPException(status_code=404, detail="No report available")
    equations = (
        _last_report.get("extracted_content", {}).get("equations", [])
    )
    return equations


# ---------------------------------------------------------------------------
# Paper fetching (download PDF + metadata, no analysis)
# ---------------------------------------------------------------------------

class FetchRequest(BaseModel):
    source: str  # arXiv URL, arXiv ID, DOI, or PDF URL


class FetchResponse(BaseModel):
    source_type: str
    pdf_path: str
    pdf_size_bytes: int
    metadata: Optional[dict] = None


@app.post("/fetch")
async def fetch_paper(req: FetchRequest):
    """Download a paper PDF from arXiv URL / ID / DOI / URL.

    Returns the local PDF path and any metadata found, without running analysis.
    """
    from research_analyser.input_handler import InputHandler
    from research_analyser.models import PaperInput

    handler = InputHandler(temp_dir=config.app.temp_dir)

    try:
        source_type = handler.detect_source_type(req.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    paper_input = PaperInput(source_value=req.source, source_type=source_type)

    try:
        pdf_path = await handler.resolve(paper_input)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    pdf_size = pdf_path.stat().st_size

    # Try to get metadata if arXiv
    metadata = None
    if source_type.value == "arxiv_id":
        arxiv_id = handler._extract_arxiv_id(req.source)
        metadata = await handler._fetch_arxiv_metadata(arxiv_id)

    return FetchResponse(
        source_type=source_type.value,
        pdf_path=str(pdf_path),
        pdf_size_bytes=pdf_size,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

class DeviceInfoResponse(BaseModel):
    device_type: str  # "apple_silicon", "cuda", "cpu"
    device_name: str  # e.g., "Apple M4 Pro", "NVIDIA RTX 4090", "CPU"
    mps_available: bool
    cuda_available: bool
    recommended_variant: str  # "apple_silicon" or "standard"


def _detect_device() -> dict:
    """Auto-detect compute device: Apple Silicon MPS, NVIDIA CUDA, or CPU."""
    info = {
        "device_type": "cpu",
        "device_name": "CPU",
        "mps_available": False,
        "cuda_available": False,
        "recommended_variant": "standard",
    }

    # Check for Apple Silicon (MPS)
    import platform
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        info["mps_available"] = True
        info["device_type"] = "apple_silicon"
        info["recommended_variant"] = "apple_silicon"
        # Get chip name
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                info["device_name"] = result.stdout.strip()
            else:
                info["device_name"] = "Apple Silicon"
        except Exception:
            info["device_name"] = "Apple Silicon"

        # Verify MPS via torch if available
        try:
            import torch
            info["mps_available"] = torch.backends.mps.is_available()
        except ImportError:
            info["mps_available"] = True  # arm64 Mac ≈ MPS capable

    # Check for NVIDIA CUDA
    try:
        import torch
        if torch.cuda.is_available():
            info["cuda_available"] = True
            if not info["mps_available"]:
                info["device_type"] = "cuda"
                info["recommended_variant"] = "standard"
                try:
                    info["device_name"] = torch.cuda.get_device_name(0)
                except Exception:
                    info["device_name"] = "NVIDIA GPU"
    except ImportError:
        pass

    return info


@app.get("/device/info")
async def device_info():
    """Auto-detect compute device (Apple Silicon / NVIDIA CUDA / CPU)."""
    return DeviceInfoResponse(**_detect_device())


# ---------------------------------------------------------------------------
# MonkeyOCR offline model management
# ---------------------------------------------------------------------------

# Directory where Apple Silicon MonkeyOCR is cloned
_APPLE_SILICON_DIR = Path.home() / ".cache" / "research-analyser" / "MonkeyOCR-Apple-Silicon"
_APPLE_SILICON_REPO = "https://huggingface.co/Jimmi42/MonkeyOCR-Apple-Silicon"


class MonkeyOCRStatusResponse(BaseModel):
    installed: bool
    model_name: str
    model_path: Optional[str] = None
    size_mb: Optional[float] = None
    file_count: Optional[int] = None
    complete: Optional[bool] = None
    expected_size_gb: Optional[float] = None
    cache_dir: Optional[str] = None
    variant: str = "standard"  # "standard" or "apple_silicon"
    device_type: str = "cpu"   # "apple_silicon", "cuda", "cpu"
    message: str


class MonkeyOCRDownloadResponse(BaseModel):
    success: bool
    model_name: str
    model_path: Optional[str] = None
    size_mb: Optional[float] = None
    file_count: Optional[int] = None
    variant: str = "standard"
    message: str


# Expected sizes for known models — used for download integrity validation
_EXPECTED_SIZES_GB: dict[str, float] = {
    "MonkeyOCR-pro-3B": 3.0,
}


def _find_monkey_ocr_model(
    model_name: str = "MonkeyOCR-pro-3B",
) -> dict:
    """Check whether MonkeyOCR model weights exist locally.

    Returns dict with keys: installed, model_path, size_mb, file_count,
    complete, expected_size_gb, cache_dir.
    """
    info: dict = {
        "installed": False,
        "model_path": None,
        "size_mb": None,
        "file_count": None,
        "complete": None,
        "expected_size_gb": _EXPECTED_SIZES_GB.get(model_name),
        "cache_dir": None,
    }

    try:
        from huggingface_hub import scan_cache_dir
        try:
            cache_info = scan_cache_dir()
            info["cache_dir"] = str(cache_info.cache_dir)
            for repo in cache_info.repos:
                if model_name.lower() in repo.repo_id.lower():
                    repo_path = Path(repo.repo_path)
                    info["installed"] = True
                    info["model_path"] = str(repo_path)

                    # Calculate total size and file count from blobs
                    total_bytes = 0
                    n_files = 0
                    try:
                        blobs_dir = repo_path / "blobs"
                        if blobs_dir.exists():
                            for f in blobs_dir.rglob("*"):
                                if f.is_file():
                                    total_bytes += f.stat().st_size
                                    n_files += 1
                        else:
                            # count from snapshots
                            for f in repo_path.rglob("*"):
                                if f.is_file():
                                    total_bytes += f.stat().st_size
                                    n_files += 1
                    except OSError:
                        pass

                    info["size_mb"] = round(total_bytes / (1024 * 1024), 1)
                    info["file_count"] = n_files

                    # Completeness heuristic:
                    # 1. Must have config.json
                    # 2. Must have at least one large safetensors/bin (>100 MB)
                    # 3. If expected size is known, actual must be >= 80% of it
                    has_config = False
                    has_weights = False
                    try:
                        for snap in (repo_path / "snapshots").iterdir():
                            for sf in snap.rglob("*"):
                                name = sf.name.lower()
                                if name == "config.json":
                                    has_config = True
                                if sf.is_file() and sf.stat().st_size > 100_000_000:
                                    has_weights = True
                    except (OSError, StopIteration):
                        pass

                    structurally_ok = has_config and has_weights
                    # Size-based sanity check
                    expected_gb = _EXPECTED_SIZES_GB.get(model_name)
                    if expected_gb and info["size_mb"]:
                        actual_gb = info["size_mb"] / 1024
                        size_ok = actual_gb >= (expected_gb * 0.8)
                    else:
                        size_ok = True  # can't verify — assume ok
                    info["complete"] = structurally_ok and size_ok
                    return info
        except Exception:
            # CacheNotFound or other error — set default cache dir
            import os
            info["cache_dir"] = os.path.expanduser("~/.cache/huggingface/hub")
    except ImportError:
        pass

    # Fallback: check if monkeyocr package is importable (not local shim)
    try:
        import monkeyocr
        mod_path = Path(monkeyocr.__file__).resolve()
        # The local monkeyocr.py shim is in the project root — not a real install
        project_root = Path(__file__).resolve().parent.parent
        if mod_path.parent == project_root:
            # Local shim — monkeyocr is NOT really installed
            info["installed"] = False
            info["complete"] = False
            info["model_path"] = None
        else:
            # Real monkeyocr package
            info["installed"] = True
            info["complete"] = True
            info["model_path"] = str(mod_path.parent)
        return info
    except ImportError:
        pass

    return info


def _find_apple_silicon_ocr() -> dict:
    """Check whether Apple Silicon MonkeyOCR is installed locally.

    Returns dict with keys: installed, model_path, size_mb, file_count, complete.
    """
    info: dict = {
        "installed": False,
        "model_path": None,
        "size_mb": None,
        "file_count": None,
        "complete": None,
    }

    if not _APPLE_SILICON_DIR.exists():
        return info

    # Check for key files that indicate a complete setup
    setup_sh = _APPLE_SILICON_DIR / "setup.sh"
    main_py = _APPLE_SILICON_DIR / "main.py"
    config_yaml = _APPLE_SILICON_DIR / "model_configs_mps.yaml"
    monkey_dir = _APPLE_SILICON_DIR / "MonkeyOCR"

    if not (setup_sh.exists() and main_py.exists()):
        return info

    info["installed"] = True
    info["model_path"] = str(_APPLE_SILICON_DIR)

    # Calculate size
    total_bytes = 0
    n_files = 0
    try:
        for f in _APPLE_SILICON_DIR.rglob("*"):
            if f.is_file():
                total_bytes += f.stat().st_size
                n_files += 1
    except OSError:
        pass
    info["size_mb"] = round(total_bytes / (1024 * 1024), 1)
    info["file_count"] = n_files

    # Completeness: must have MonkeyOCR subdir (created by setup.sh),
    # model_configs_mps.yaml, and a venv
    has_monkey = monkey_dir.exists() and (monkey_dir / "magic_pdf").exists()
    has_config = config_yaml.exists()
    has_venv = (_APPLE_SILICON_DIR / ".venv").exists()
    info["complete"] = has_monkey and has_config and has_venv

    return info


@app.get("/monkeyocr/status")
async def monkeyocr_status():
    """Check whether MonkeyOCR model is downloaded and ready.

    Also reports device auto-detection (apple_silicon / cuda / cpu)
    and which variant is installed.
    """
    model_name = config.ocr.model
    device = _detect_device()
    device_type = device["device_type"]

    # Check Apple Silicon variant first (on Mac)
    apple_info = _find_apple_silicon_ocr()
    if apple_info["installed"]:
        size_str = f"{apple_info['size_mb']} MB" if apple_info["size_mb"] else "unknown size"
        complete_str = "fully set up" if apple_info["complete"] else "setup incomplete"
        return MonkeyOCRStatusResponse(
            installed=True,
            model_name="MonkeyOCR-Apple-Silicon (MLX)",
            model_path=apple_info["model_path"],
            size_mb=apple_info["size_mb"],
            file_count=apple_info["file_count"],
            complete=apple_info["complete"],
            expected_size_gb=None,
            cache_dir=str(_APPLE_SILICON_DIR.parent),
            variant="apple_silicon",
            device_type=device_type,
            message=f"MonkeyOCR Apple Silicon (MLX) is installed ({size_str}, {complete_str}).",
        )

    # Check standard HuggingFace variant
    info = _find_monkey_ocr_model(model_name)

    if info["installed"]:
        size_str = f"{info['size_mb']} MB" if info["size_mb"] else "unknown size"
        complete_str = "fully downloaded" if info["complete"] else "possibly incomplete"
        exp_str = ""
        if info.get("expected_size_gb"):
            exp_str = f", expected ~{info['expected_size_gb']} GB"
        return MonkeyOCRStatusResponse(
            installed=True,
            model_name=model_name,
            model_path=info["model_path"],
            size_mb=info["size_mb"],
            file_count=info["file_count"],
            complete=info["complete"],
            expected_size_gb=info.get("expected_size_gb"),
            cache_dir=info["cache_dir"],
            variant="standard",
            device_type=device_type,
            message=f"MonkeyOCR ({model_name}) is installed ({size_str}{exp_str}, {complete_str}).",
        )

    # Not installed — recommend variant based on device
    rec = "Apple Silicon (MLX)" if device_type == "apple_silicon" else model_name
    return MonkeyOCRStatusResponse(
        installed=False,
        model_name=model_name,
        expected_size_gb=info.get("expected_size_gb"),
        cache_dir=info["cache_dir"],
        variant="none",
        device_type=device_type,
        message=f"MonkeyOCR is not installed. Recommended: {rec} for your {device['device_name']}.",
    )


@app.post("/monkeyocr/download")
async def monkeyocr_download():
    """Trigger download of MonkeyOCR model weights.

    Auto-detects device and selects the appropriate variant:
    - Apple Silicon → clones Apple Silicon MLX repo + runs setup.sh
    - NVIDIA/CPU → downloads standard model from HuggingFace

    Requires HF_TOKEN to be set for gated models.
    """
    model_name = config.ocr.model
    device = _detect_device()

    # Auto-select: Apple Silicon uses the MLX variant
    if device["device_type"] == "apple_silicon":
        return await _setup_apple_silicon_ocr()

    # Check if standard model is already installed
    info = _find_monkey_ocr_model(model_name)
    if info["installed"] and info.get("complete"):
        return MonkeyOCRDownloadResponse(
            success=True,
            model_name=model_name,
            model_path=info["model_path"],
            size_mb=info["size_mb"],
            file_count=info["file_count"],
            variant="standard",
            message=f"MonkeyOCR ({model_name}) is already downloaded.",
        )

    # Attempt download
    try:
        from huggingface_hub import snapshot_download
        import os

        hf_token = os.getenv("HF_TOKEN") or config.hf_token
        repo_id = f"echo840/{model_name}"

        # Respect SKIP_SSL_VERIFICATION for corporate/firewall environments
        skip_ssl = os.getenv("SKIP_SSL_VERIFICATION", "").lower() in ("1", "true", "yes")
        if skip_ssl:
            os.environ["HF_HUB_DISABLE_SSL"] = "1"
            os.environ["CURL_CA_BUNDLE"] = ""
            os.environ["REQUESTS_CA_BUNDLE"] = ""
            import ssl
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            # Monkey-patch requests session used by huggingface_hub
            import requests
            old_request = requests.Session.request
            def _no_verify_request(self, *args, **kwargs):
                kwargs.setdefault("verify", False)
                return old_request(self, *args, **kwargs)
            requests.Session.request = _no_verify_request  # type: ignore
            logger.warning("SSL verification disabled for HuggingFace download")

        logger.info("Downloading MonkeyOCR model: %s", repo_id)
        local_dir = await asyncio.to_thread(
            snapshot_download,
            repo_id=repo_id,
            token=hf_token,
        )
        logger.info("MonkeyOCR downloaded to: %s", local_dir)

        # Get post-download size info
        post_info = _find_monkey_ocr_model(model_name)

        return MonkeyOCRDownloadResponse(
            success=True,
            model_name=model_name,
            model_path=str(local_dir),
            size_mb=post_info.get("size_mb"),
            file_count=post_info.get("file_count"),
            variant="standard",
            message=f"Successfully downloaded {model_name}.",
        )
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="huggingface_hub is not installed. Run: pip install huggingface_hub",
        )
    except Exception as exc:
        logger.error("MonkeyOCR download failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {exc}",
        ) from exc


async def _setup_apple_silicon_ocr() -> MonkeyOCRDownloadResponse:
    """Clone and set up Apple Silicon MonkeyOCR with MLX-VLM acceleration.

    Steps:
    1. git clone the HuggingFace repo
    2. Clean up broken inner MonkeyOCR/ subdir if needed
    3. chmod +x setup.sh && ./setup.sh  (with SSL bypass env vars)
    4. Verify the setup produced MonkeyOCR/ subdir with magic_pdf + .venv
    """
    import subprocess

    model_name = "MonkeyOCR-Apple-Silicon"

    # Check if already set up
    apple_info = _find_apple_silicon_ocr()
    if apple_info["installed"] and apple_info.get("complete"):
        return MonkeyOCRDownloadResponse(
            success=True,
            model_name=model_name,
            model_path=apple_info["model_path"],
            size_mb=apple_info["size_mb"],
            file_count=apple_info["file_count"],
            variant="apple_silicon",
            message="MonkeyOCR Apple Silicon (MLX) is already set up.",
        )

    # Build subprocess environment with SSL bypass for corporate firewalls
    skip_ssl = os.getenv("SKIP_SSL_VERIFICATION", "").lower() in ("1", "true", "yes")
    sub_env: dict[str, str] | None = None
    if skip_ssl:
        sub_env = os.environ.copy()
        sub_env.update({
            # Git: skip certificate verification
            "GIT_SSL_NO_VERIFY": "1",
            # uv: use system-native TLS (trusts macOS Keychain)
            "UV_NATIVE_TLS": "true",
            # uv: allow insecure connections to download hosts
            "UV_INSECURE_HOST": (
                "github.com,objects.githubusercontent.com,"
                "pypi.org,files.pythonhosted.org,pypi.python.org,"
                "raw.githubusercontent.com,huggingface.co,"
                "cdn-lfs-us-1.hf.co,cdn-lfs.hf.co"
            ),
            # pip: trusted hosts (no TLS verification)
            "PIP_TRUSTED_HOST": (
                "pypi.org files.pythonhosted.org pypi.python.org"
            ),
            # requests / curl: disable CA bundle verification
            "REQUESTS_CA_BUNDLE": "",
            "CURL_CA_BUNDLE": "",
        })
        logger.warning("SSL verification disabled for Apple Silicon OCR setup subprocesses")

    try:
        parent_dir = _APPLE_SILICON_DIR.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Clone the repo (or pull if partially cloned)
        if _APPLE_SILICON_DIR.exists():
            # Already exists — try git pull
            logger.info("Apple Silicon OCR dir exists, pulling updates…")
            await asyncio.to_thread(
                subprocess.run,
                ["git", "pull"],
                cwd=str(_APPLE_SILICON_DIR),
                capture_output=True,
                text=True,
                timeout=120,
                env=sub_env,
            )
        else:
            logger.info("Cloning Apple Silicon MonkeyOCR from %s", _APPLE_SILICON_REPO)
            clone_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "clone", _APPLE_SILICON_REPO, str(_APPLE_SILICON_DIR)],
                capture_output=True,
                text=True,
                timeout=300,
                env=sub_env,
            )
            if clone_result.returncode != 0:
                raise RuntimeError(
                    f"git clone failed: {clone_result.stderr.strip()}"
                )

        # Step 2: Clean up broken inner MonkeyOCR/ subdir from partial runs
        inner_monkey = _APPLE_SILICON_DIR / "MonkeyOCR"
        if inner_monkey.exists() and not (inner_monkey / ".git").exists():
            logger.warning("Removing broken MonkeyOCR/ subdir (no .git) for clean re-clone")
            import shutil
            shutil.rmtree(inner_monkey, ignore_errors=True)

        # Step 3: chmod +x setup.sh and run it
        setup_sh = _APPLE_SILICON_DIR / "setup.sh"
        if not setup_sh.exists():
            raise RuntimeError("setup.sh not found in cloned repo")

        logger.info("Running setup.sh for Apple Silicon MonkeyOCR…")
        await asyncio.to_thread(
            subprocess.run,
            ["chmod", "+x", str(setup_sh)],
            timeout=10,
        )

        setup_result = await asyncio.to_thread(
            subprocess.run,
            ["bash", str(setup_sh)],
            cwd=str(_APPLE_SILICON_DIR),
            capture_output=True,
            text=True,
            timeout=600,  # setup can take a while (downloads models)
            env=sub_env,
        )

        if setup_result.returncode != 0:
            # setup.sh may fail at the model-download step (SSL issues) but
            # the actual install (venv + dependencies + MLX patches) can still
            # be complete.  Verify before giving up.
            logger.warning(
                "setup.sh exited %d — checking if the install is usable anyway…",
                setup_result.returncode,
            )
            post_info = _find_apple_silicon_ocr()
            if not (post_info["installed"] and post_info.get("complete")):
                logger.error("setup.sh failed: %s", setup_result.stderr[-2000:])
                raise RuntimeError(
                    f"setup.sh failed (exit {setup_result.returncode}): "
                    + setup_result.stderr[-500:]
                )
            logger.info(
                "setup.sh had non-zero exit but install looks complete — continuing"
            )
        else:
            logger.info("Apple Silicon MonkeyOCR setup completed")

        # Step 4: Verify
        post_info = _find_apple_silicon_ocr()
        if not post_info["installed"]:
            raise RuntimeError("Setup completed but MonkeyOCR-Apple-Silicon not detected")

        return MonkeyOCRDownloadResponse(
            success=True,
            model_name=model_name,
            model_path=post_info["model_path"],
            size_mb=post_info["size_mb"],
            file_count=post_info["file_count"],
            variant="apple_silicon",
            message="MonkeyOCR Apple Silicon (MLX) set up successfully.",
        )

    except Exception as exc:
        logger.error("Apple Silicon OCR setup failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Apple Silicon setup failed: {exc}",
        ) from exc


@app.post("/monkeyocr/setup-apple-silicon")
async def monkeyocr_setup_apple_silicon():
    """Explicitly set up Apple Silicon MonkeyOCR (even on non-Mac for testing)."""
    return await _setup_apple_silicon_ocr()


@app.delete("/monkeyocr/delete")
async def monkeyocr_delete():
    """Delete the locally cached MonkeyOCR model to free disk space.

    Handles both Apple Silicon and standard variants.
    """
    import shutil

    # Check Apple Silicon variant first
    apple_info = _find_apple_silicon_ocr()
    if apple_info["installed"] and apple_info["model_path"]:
        apple_path = Path(apple_info["model_path"])
        deleted_mb = apple_info.get("size_mb", 0) or 0
        try:
            if apple_path.exists():
                shutil.rmtree(apple_path)
                logger.info("Deleted Apple Silicon MonkeyOCR: %s", apple_path)
            return {
                "success": True,
                "deleted_path": str(apple_path),
                "freed_mb": round(deleted_mb, 1),
                "message": f"Deleted MonkeyOCR Apple Silicon ({round(deleted_mb, 1)} MB freed).",
            }
        except Exception as exc:
            logger.error("Failed to delete Apple Silicon OCR: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Delete failed: {exc}",
            ) from exc

    # Fall back to standard variant
    model_name = config.ocr.model
    info = _find_monkey_ocr_model(model_name)

    if not info["installed"] or not info["model_path"]:
        raise HTTPException(
            status_code=404,
            detail="MonkeyOCR is not installed locally (neither Apple Silicon nor standard).",
        )

    model_path = Path(info["model_path"])
    deleted_mb = info.get("size_mb", 0) or 0

    try:
        # Try using huggingface_hub's cache management first
        try:
            from huggingface_hub import scan_cache_dir
            cache_info = scan_cache_dir()
            for repo in cache_info.repos:
                if model_name.lower() in repo.repo_id.lower():
                    # Use the proper HF cache deletion strategy
                    delete_strategy = cache_info.delete_revisions(
                        *[rev.commit_hash for rev in repo.revisions]
                    )
                    delete_strategy.execute()
                    logger.info("Deleted MonkeyOCR via HF cache manager: %s", repo.repo_id)
                    return {
                        "success": True,
                        "deleted_path": str(model_path),
                        "freed_mb": round(deleted_mb, 1),
                        "message": f"Deleted {model_name} ({round(deleted_mb, 1)} MB freed).",
                    }
        except Exception as hf_err:
            logger.warning("HF cache deletion failed, falling back to shutil: %s", hf_err)

        # Fallback: just remove the directory tree
        if model_path.exists():
            shutil.rmtree(model_path)
            logger.info("Deleted MonkeyOCR directory: %s", model_path)
        return {
            "success": True,
            "deleted_path": str(model_path),
            "freed_mb": round(deleted_mb, 1),
            "message": f"Deleted {model_name} ({round(deleted_mb, 1)} MB freed).",
        }
    except Exception as exc:
        logger.error("Failed to delete MonkeyOCR: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Text → Diagram generation (standalone PaperBanana)
# ---------------------------------------------------------------------------

class DiagramRequest(BaseModel):
    text: str
    diagram_type: str = "methodology"  # methodology | architecture | results
    engine: str = "paperbanana"  # "paperbanana" or "beautiful_mermaid"


class DiagramResponse(BaseModel):
    diagram_type: str
    image_path: Optional[str] = None
    svg_path: Optional[str] = None
    png_path: Optional[str] = None
    mermaid_code: Optional[str] = None
    is_fallback: bool = False
    message: Optional[str] = None


def _text_to_mermaid(text: str, diagram_type: str) -> str:
    """Parse free-form text into a meaningful Mermaid diagram.

    Splits text into sentences/clauses and builds a flowchart from them.
    """
    import re as _re

    # Split into sentences or semicolon-separated clauses
    raw_parts = _re.split(r'(?<=[.!?;])\s+|\n+', text.strip())
    # Clean and deduplicate
    steps = []
    for p in raw_parts:
        p = p.strip().rstrip('.!?;').strip()
        if len(p) > 5 and p not in steps:
            steps.append(p)

    if not steps:
        steps = [text.strip()[:80]]

    # Truncate labels to fit in boxes
    max_label = 60
    labels = [s[:max_label] + ("…" if len(s) > max_label else "") for s in steps]

    # Escape double quotes
    labels = [l.replace('"', "'") for l in labels]

    if diagram_type == "architecture":
        nodes = [f'    N{i}["{l}"]' for i, l in enumerate(labels)]
        edges = [f"    N{i} --> N{i+1}" for i in range(len(labels) - 1)]
        return "graph TD\n" + "\n".join(nodes) + "\n" + "\n".join(edges)

    if diagram_type == "results":
        nodes = [f'    R{i}["{l}"]' for i, l in enumerate(labels)]
        edges = []
        if len(labels) >= 2:
            edges = [f"    R{i} --> R{i+1}" for i in range(len(labels) - 1)]
        return "graph LR\n" + "\n".join(nodes) + "\n" + "\n".join(edges)

    # Default: methodology (TD flowchart)
    nodes = [f'    M{i}["{l}"]' for i, l in enumerate(labels)]
    edges = [f"    M{i} --> M{i+1}" for i in range(len(labels) - 1)]
    return "graph TD\n" + "\n".join(nodes) + "\n" + "\n".join(edges)


def _upscale_svg(svg_content: str, scale: int = 4) -> str:
    """Scale the SVG width/height attributes for higher resolution rendering.

    Beautiful Mermaid outputs SVGs with small width/height matching the viewBox.
    We multiply width and height by `scale` while keeping viewBox the same,
    producing a crisp large image.
    """
    import re as _re

    def _scale_attr(match):
        val = float(match.group(1))
        return f'{match.group(0).split("=")[0]}="{val * scale}"'

    svg_content = _re.sub(r'width="([\d.]+)"', _scale_attr, svg_content, count=1)
    svg_content = _re.sub(r'height="([\d.]+)"', _scale_attr, svg_content, count=1)
    return svg_content


@app.post("/diagrams/generate")
async def generate_diagram(req: DiagramRequest):
    """Generate a diagram from free-form text.

    Supports two engines:
    - paperbanana: PaperBanana pipeline (requires GOOGLE_API_KEY)
    - beautiful_mermaid: Local Mermaid → SVG/PNG rendering (no API key needed)
    """
    from research_analyser.models import ExtractedContent, Section

    # Build a minimal ExtractedContent with just the user's text
    content = ExtractedContent(
        full_text=req.text,
        title="User-provided text",
        authors=[],
        abstract=req.text[:500],
        sections=[Section(title="Content", level=1, content=req.text)],
        equations=[],
        figures=[],
        tables=[],
        references=[],
    )

    if req.engine == "beautiful_mermaid":
        # Use Beautiful Mermaid (local, no API key)
        try:
            # Parse free-text into meaningful mermaid code
            mermaid_code = _text_to_mermaid(req.text, req.diagram_type)
            import subprocess
            # Prefer bundled script (works with Node.js >=22 where TS
            # stripping in node_modules is unsupported)
            render_script = analyser._beautiful_mermaid_dir / "render.bundle.mjs"
            if not render_script.exists():
                render_script = analyser._beautiful_mermaid_dir / "render.mjs"
            if not render_script.exists():
                raise HTTPException(
                    status_code=501,
                    detail=f"Beautiful Mermaid render script not found in {analyser._beautiful_mermaid_dir}",
                )

            diagrams_dir = Path(config.app.output_dir).resolve() / "diagrams"
            diagrams_dir.mkdir(parents=True, exist_ok=True)
            svg_path = diagrams_dir / f"{req.diagram_type}.svg"
            png_path = diagrams_dir / f"{req.diagram_type}.png"

            proc = subprocess.run(
                ["node", str(render_script), "github-dark"],
                input=mermaid_code,
                capture_output=True,
                text=True,
                cwd=str(analyser._beautiful_mermaid_dir),
                timeout=30,
            )
            if proc.returncode != 0:
                raise HTTPException(status_code=500, detail=f"Mermaid render failed: {proc.stderr}")

            svg_content = proc.stdout

            # Scale up SVG for high resolution: replace viewBox dimensions
            # to produce a larger default rendering
            svg_content = _upscale_svg(svg_content, scale=4)

            svg_path.write_text(svg_content, encoding="utf-8")
            logger.info("SVG diagram saved to %s (%d bytes)", svg_path, len(svg_content))

            # Convert SVG → high-res PNG
            png_generated = False
            try:
                import cairosvg
                cairosvg.svg2png(
                    bytestring=svg_content.encode(),
                    write_to=str(png_path),
                    output_width=2400,
                )
                png_generated = True
                logger.info("PNG diagram saved to %s", png_path)
            except (ImportError, OSError) as exc:
                logger.warning("cairosvg PNG conversion unavailable: %s", exc)

            final_path = png_path if png_generated else svg_path

            return DiagramResponse(
                diagram_type=req.diagram_type,
                image_path=str(final_path.resolve()),
                svg_path=str(svg_path.resolve()),
                png_path=str(png_path.resolve()) if png_generated else None,
                mermaid_code=mermaid_code,
                is_fallback=False,
                message=(
                    "Diagram generated with Beautiful Mermaid."
                    + ("" if png_generated else " PNG unavailable (install cairo).")
                ),
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Beautiful Mermaid generation failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # PaperBanana engine (default)
    from research_analyser.diagram_generator import DiagramGenerator

    generator = DiagramGenerator(
        output_dir=str(config.app.output_dir) + "/diagrams",
    )

    try:
        diagrams = await generator.generate(
            content,
            diagram_types=[req.diagram_type],
        )

        if not diagrams:
            return DiagramResponse(
                diagram_type=req.diagram_type,
                message="No diagram was generated.",
            )

        d = diagrams[0]
        img_path = Path(d.image_path).resolve() if d.image_path else None
        return DiagramResponse(
            diagram_type=req.diagram_type,
            image_path=str(img_path) if img_path else None,
            mermaid_code=getattr(d, "mermaid_code", None),
            is_fallback=getattr(d, "is_fallback", False),
            message="Diagram generated with PaperBanana.",
        )
    except Exception as exc:
        logger.error("Diagram generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/diagrams/generate/stream")
async def generate_diagram_stream(req: DiagramRequest):
    """SSE-streaming version of /diagrams/generate.

    Emits ``progress`` events with ``{pct, message}`` during generation so the
    VS Code extension can update its progress notification in real time, then
    emits a final ``complete`` event with the DiagramResponse payload.
    """
    if not _SSE_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="SSE streaming not available. Install sse-starlette: pip install sse-starlette",
        )

    from research_analyser.models import ExtractedContent, Section

    content = ExtractedContent(
        full_text=req.text,
        title="User-provided text",
        authors=[],
        abstract=req.text[:500],
        sections=[Section(title="Content", level=1, content=req.text)],
        equations=[],
        figures=[],
        tables=[],
        references=[],
    )

    async def _event_generator():
        try:
            if req.engine == "beautiful_mermaid":
                # ── Beautiful Mermaid (local, synchronous steps) ─────────────
                yield {
                    "event": "progress",
                    "data": json.dumps({"pct": 10, "message": "Generating Mermaid code…"}),
                }
                mermaid_code = _text_to_mermaid(req.text, req.diagram_type)

                render_script = analyser._beautiful_mermaid_dir / "render.bundle.mjs"
                if not render_script.exists():
                    render_script = analyser._beautiful_mermaid_dir / "render.mjs"
                if not render_script.exists():
                    yield {
                        "event": "error",
                        "data": json.dumps({"message": f"Beautiful Mermaid render script not found in {analyser._beautiful_mermaid_dir}"}),
                    }
                    return

                diagrams_dir = Path(config.app.output_dir).resolve() / "diagrams"
                diagrams_dir.mkdir(parents=True, exist_ok=True)
                svg_path = diagrams_dir / f"{req.diagram_type}.svg"
                png_path = diagrams_dir / f"{req.diagram_type}.png"

                yield {
                    "event": "progress",
                    "data": json.dumps({"pct": 40, "message": "Rendering SVG…"}),
                }
                import subprocess as _sp
                proc = await asyncio.to_thread(
                    _sp.run,
                    ["node", str(render_script), "github-dark"],
                    input=mermaid_code,
                    capture_output=True,
                    text=True,
                    cwd=str(analyser._beautiful_mermaid_dir),
                    timeout=30,
                )
                if proc.returncode != 0:
                    yield {
                        "event": "error",
                        "data": json.dumps({"message": f"Mermaid render failed: {proc.stderr}"}),
                    }
                    return

                svg_content = _upscale_svg(proc.stdout, scale=4)
                svg_path.write_text(svg_content, encoding="utf-8")

                yield {
                    "event": "progress",
                    "data": json.dumps({"pct": 80, "message": "Converting to PNG…"}),
                }
                png_generated = False
                try:
                    import cairosvg as _cairosvg
                    await asyncio.to_thread(
                        _cairosvg.svg2png,
                        bytestring=svg_content.encode(),
                        write_to=str(png_path),
                        output_width=2400,
                    )
                    png_generated = True
                except (ImportError, OSError) as _exc:
                    logger.warning("cairosvg PNG conversion unavailable: %s", _exc)

                final_path = png_path if png_generated else svg_path
                result = DiagramResponse(
                    diagram_type=req.diagram_type,
                    image_path=str(final_path.resolve()),
                    svg_path=str(svg_path.resolve()),
                    png_path=str(png_path.resolve()) if png_generated else None,
                    mermaid_code=mermaid_code,
                    is_fallback=False,
                    message=(
                        "Diagram generated with Beautiful Mermaid."
                        + ("" if png_generated else " PNG unavailable (install cairo).")
                    ),
                )
                yield {
                    "event": "complete",
                    "data": json.dumps(result.model_dump(), default=_json_default),
                }

            else:
                # ── PaperBanana pipeline ─────────────────────────────────────
                # Emit the five named pipeline stages with approximate timing
                # while the async task runs in the background.
                from research_analyser.diagram_generator import DiagramGenerator

                pb_stages = [
                    (10, "Phase 1: Retrieval — selecting reference examples…"),
                    (25, "Phase 2: Planning — building visual description…"),
                    (45, "Phase 3: Styling — refining aesthetics…"),
                    (65, "Phase 4: Visualization — rendering image…"),
                    (85, "Phase 5: Critic — evaluating output…"),
                ]
                # Seconds to wait at each stage before advancing to the next
                stage_delays = [12, 15, 15, 25, 15]

                generator = DiagramGenerator(
                    output_dir=str(config.app.output_dir) + "/diagrams",
                )
                task = asyncio.create_task(
                    generator.generate(content, diagram_types=[req.diagram_type])
                )

                for (pct, msg), delay in zip(pb_stages, stage_delays):
                    yield {
                        "event": "progress",
                        "data": json.dumps({"pct": pct, "message": msg}),
                    }
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=delay)
                        break  # task finished before this stage's timeout
                    except asyncio.TimeoutError:
                        pass  # still running — advance to next stage label

                diagrams = await task  # get result (or propagate exception)

                if not diagrams:
                    result = DiagramResponse(
                        diagram_type=req.diagram_type,
                        message="No diagram was generated.",
                    )
                else:
                    d = diagrams[0]
                    img_path = Path(d.image_path).resolve() if d.image_path else None
                    result = DiagramResponse(
                        diagram_type=req.diagram_type,
                        image_path=str(img_path) if img_path else None,
                        mermaid_code=getattr(d, "mermaid_code", None),
                        is_fallback=getattr(d, "is_fallback", False),
                        message="Diagram generated with PaperBanana.",
                    )

                yield {
                    "event": "complete",
                    "data": json.dumps(result.model_dump(), default=_json_default),
                }

        except Exception as _exc:
            logger.error("Diagram stream generation failed: %s", _exc)
            yield {
                "event": "error",
                "data": json.dumps({"message": str(_exc)}),
            }

    return EventSourceResponse(_event_generator())
