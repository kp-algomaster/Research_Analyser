"""Text-to-speech engine using Qwen3-TTS for audio narration of paper analysis."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

import numpy as np

from research_analyser.models import AnalysisReport

logger = logging.getLogger(__name__)

# Qwen3-TTS generates audio at 24 kHz
DEFAULT_SAMPLE_RATE = 24000
MAX_CHUNK_CHARS = 500
# Short silence (0.4 s) inserted between chunks
SILENCE_DURATION = 0.4


class TTSEngine:
    """Generate audio narration of analysis reports using Qwen3-TTS."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-TTS",
        device: str = "auto",
        speaker: str = "default",
    ):
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.speaker = speaker
        self._model = None
        self._processor = None
        self._sample_rate: int = DEFAULT_SAMPLE_RATE

    # ------------------------------------------------------------------
    # Device helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        if self._model is not None:
            return

        import torch
        from transformers import AutoModel, AutoProcessor

        logger.info("Loading Qwen3-TTS model: %s (device=%s)", self.model_name, self.device)

        dtype = torch.float16 if self.device != "cpu" else torch.float32

        self._processor = AutoProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._model = AutoModel.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            torch_dtype=dtype,
        )
        self._model.to(self.device)
        self._model.eval()

        # Some TTS models expose their sample rate on the config
        if hasattr(self._model.config, "sampling_rate"):
            self._sample_rate = self._model.config.sampling_rate
        elif hasattr(self._processor, "sampling_rate"):
            self._sample_rate = self._processor.sampling_rate

        logger.info(
            "Qwen3-TTS loaded (sample_rate=%d, dtype=%s)",
            self._sample_rate,
            dtype,
        )

    # ------------------------------------------------------------------
    # Core synthesis
    # ------------------------------------------------------------------

    def _synthesize_chunk(self, text: str) -> np.ndarray:
        """Synthesize a single text chunk to a 1-D float32 numpy waveform."""
        import torch

        self._load_model()

        inputs = self._processor(
            text=text,
            return_tensors="pt",
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            output = self._model.generate(**inputs)

        # Handle common output shapes from HF TTS models
        if hasattr(output, "waveform"):
            wav = output.waveform
        elif hasattr(output, "audio"):
            wav = output.audio
        elif isinstance(output, dict):
            wav = output.get("waveform") or output.get("audio") or output.get("wav")
        else:
            wav = output

        if isinstance(wav, torch.Tensor):
            wav = wav.cpu().float().numpy()

        # Squeeze to 1-D
        wav = np.squeeze(wav)
        if wav.ndim > 1:
            wav = wav[0]
        return wav.astype(np.float32)

    # ------------------------------------------------------------------
    # Narration builder
    # ------------------------------------------------------------------

    @staticmethod
    def build_narration(report: AnalysisReport) -> str:
        """Convert an AnalysisReport into a natural-language narration script."""
        parts: list[str] = []

        # Title & authors
        title = report.extracted_content.title
        authors = report.extracted_content.authors
        parts.append(f"Analysis report for the paper: {title}.")
        if authors:
            parts.append(f"By {', '.join(authors[:5])}.")

        # Summary
        if report.summary:
            parts.append(report.summary.one_sentence)
            if report.summary.abstract_summary:
                parts.append(report.summary.abstract_summary)

        # Key findings
        if report.key_points:
            parts.append("Key findings:")
            for i, kp in enumerate(report.key_points, 1):
                parts.append(f"Finding {i}: {kp.point}. {kp.evidence}.")

        # Methodology
        if report.summary and report.summary.methodology_summary:
            parts.append("Methodology overview:")
            parts.append(report.summary.methodology_summary)

        # Results
        if report.summary and report.summary.results_summary:
            parts.append("Results:")
            parts.append(report.summary.results_summary)

        # Conclusions
        if report.summary and report.summary.conclusions:
            parts.append("Conclusions:")
            parts.append(report.summary.conclusions)

        # Review
        if report.review:
            from research_analyser.reviewer import interpret_score

            score = report.review.overall_score
            decision = interpret_score(score)
            parts.append(
                f"Peer review score: {score:.1f} out of 10, corresponding to {decision}."
            )
            if report.review.strengths:
                parts.append("Strengths identified by the review:")
                for s in report.review.strengths[:5]:
                    parts.append(f"  {s}")
            if report.review.weaknesses:
                parts.append("Weaknesses identified by the review:")
                for w in report.review.weaknesses[:5]:
                    parts.append(f"  {w}")

        # Statistics
        ec = report.extracted_content
        parts.append(
            f"The paper contains {len(ec.sections)} sections, "
            f"{len(ec.equations)} equations, {len(ec.tables)} tables, "
            f"{len(ec.figures)} figures, and {len(ec.references)} references."
        )

        parts.append("End of analysis report.")

        raw = " ".join(parts)
        return _clean_for_speech(raw)

    # ------------------------------------------------------------------
    # Text chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
        """Split text into chunks at sentence boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) + 1 > max_chars and current:
                chunks.append(current.strip())
                current = ""
            current += " " + sent
        if current.strip():
            chunks.append(current.strip())
        return chunks or [text]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize(
        self,
        report: AnalysisReport,
        output_dir: Path,
        filename: str = "analysis_audio.wav",
    ) -> Path:
        """Generate an audio WAV file narrating the analysis report.

        Returns the path to the saved WAV file.
        """
        import soundfile as sf

        narration = self.build_narration(report)
        logger.info("Narration length: %d chars", len(narration))

        chunks = self._chunk_text(narration)
        logger.info("Synthesising %d text chunks with Qwen3-TTS", len(chunks))

        silence = np.zeros(int(self._sample_rate * SILENCE_DURATION), dtype=np.float32)

        # Run synthesis in a thread so we don't block the event loop
        loop = asyncio.get_event_loop()
        audio_parts: list[np.ndarray] = []
        for idx, chunk in enumerate(chunks, 1):
            logger.info("  Chunk %d/%d (%d chars)", idx, len(chunks), len(chunk))
            wav = await loop.run_in_executor(None, self._synthesize_chunk, chunk)
            audio_parts.append(wav)
            audio_parts.append(silence)

        full_audio = np.concatenate(audio_parts)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        sf.write(str(output_path), full_audio, samplerate=self._sample_rate)
        logger.info("Audio saved: %s (%.1f s)", output_path, len(full_audio) / self._sample_rate)

        return output_path


# ------------------------------------------------------------------
# Text cleaning helpers
# ------------------------------------------------------------------


def _clean_for_speech(text: str) -> str:
    """Strip markdown / LaTeX artefacts so the narration reads naturally."""
    # Remove LaTeX math blocks
    text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$]+\$", "", text)
    # Remove markdown bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove markdown links, keep label text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove markdown headers
    text = re.sub(r"#{1,6}\s*", "", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text
