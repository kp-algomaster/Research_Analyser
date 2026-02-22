"""Utilities for comparing local review outputs against external review systems."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from research_analyser.reviewer import interpret_score


@dataclass
class ReviewSnapshot:
    source: str
    overall_score: Optional[float] = None
    soundness: Optional[float] = None
    presentation: Optional[float] = None
    contribution: Optional[float] = None
    confidence: Optional[float] = None


def _extract_float(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _from_dict(payload: dict, source: str) -> ReviewSnapshot:
    return ReviewSnapshot(
        source=source,
        overall_score=payload.get("overall_score") or payload.get("review_score") or payload.get("overall"),
        soundness=payload.get("soundness"),
        presentation=payload.get("presentation"),
        contribution=payload.get("contribution"),
        confidence=payload.get("confidence"),
    )


def parse_external_review(path: Path) -> ReviewSnapshot:
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        return _from_dict(payload, source=f"external:{path.name}")

    return ReviewSnapshot(
        source=f"external:{path.name}",
        overall_score=_extract_float(r"overall(?:\s+score)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text),
        soundness=_extract_float(r"soundness\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text),
        presentation=_extract_float(r"presentation\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text),
        contribution=_extract_float(r"contribution\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text),
        confidence=_extract_float(r"confidence\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text),
    )


def parse_local_review(output_dir: Path) -> ReviewSnapshot:
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.exists():
        return ReviewSnapshot(source="local", overall_score=None)

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    spec_scores = {}
    spec_path = output_dir / "spec_output.md"
    if spec_path.exists():
        match = re.search(
            r"## Review Scores \(Structured\)\s*```json\s*(\{.*?\})\s*```",
            spec_path.read_text(encoding="utf-8"),
            flags=re.DOTALL,
        )
        if match:
            try:
                spec_scores = json.loads(match.group(1))
            except json.JSONDecodeError:
                spec_scores = {}

    dimensions = spec_scores.get("dimensions", {}) if isinstance(spec_scores, dict) else {}

    def dim_score(name: str) -> Optional[float]:
        node = dimensions.get(name, {})
        value = node.get("score") if isinstance(node, dict) else None
        return float(value) if value is not None else None

    return ReviewSnapshot(
        source="local",
        overall_score=payload.get("review_score") or spec_scores.get("overall"),
        soundness=dim_score("soundness"),
        presentation=dim_score("presentation"),
        contribution=dim_score("contribution"),
        confidence=spec_scores.get("confidence"),
    )


def _fmt(value: Optional[float]) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _delta(local: Optional[float], external: Optional[float]) -> str:
    if local is None or external is None:
        return "n/a"
    return f"{(local - external):+.2f}"


def build_comparison_markdown(local: ReviewSnapshot, external: ReviewSnapshot) -> str:
    lines: list[str] = []
    lines.append("# Review Comparison")
    lines.append("")
    lines.append(f"Local source: `{local.source}`")
    lines.append(f"External source: `{external.source}`")
    lines.append("")
    lines.append("## Score Table")
    lines.append("")
    lines.append("| Metric | Local | External | Delta (Local-External) |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Overall | {_fmt(local.overall_score)} | {_fmt(external.overall_score)} | {_delta(local.overall_score, external.overall_score)} |")
    lines.append(f"| Soundness | {_fmt(local.soundness)} | {_fmt(external.soundness)} | {_delta(local.soundness, external.soundness)} |")
    lines.append(f"| Presentation | {_fmt(local.presentation)} | {_fmt(external.presentation)} | {_delta(local.presentation, external.presentation)} |")
    lines.append(f"| Contribution | {_fmt(local.contribution)} | {_fmt(external.contribution)} | {_delta(local.contribution, external.contribution)} |")
    lines.append(f"| Confidence | {_fmt(local.confidence)} | {_fmt(external.confidence)} | {_delta(local.confidence, external.confidence)} |")
    lines.append("")

    if local.overall_score is not None:
        lines.append(f"Local decision: **{interpret_score(local.overall_score)}**")
    else:
        lines.append("Local decision: **n/a**")

    if external.overall_score is not None:
        lines.append(f"External decision: **{interpret_score(external.overall_score)}**")
    else:
        lines.append("External decision: **n/a**")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `n/a` means the score was not found in the provided source.")
    lines.append("- For best results, provide external review as JSON with keys: `overall_score`, `soundness`, `presentation`, `contribution`, `confidence`.")

    return "\n".join(lines)
