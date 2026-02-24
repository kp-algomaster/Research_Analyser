"""FastAPI server for Research Analyser."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

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

            yield {"event": "complete", "data": json.dumps(_last_report)}
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
