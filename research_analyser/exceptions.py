"""Custom exceptions for the Research Analyser pipeline."""


class ResearchAnalyserError(Exception):
    """Base exception for all Research Analyser errors."""


class InputError(ResearchAnalyserError):
    """Invalid or unreachable input source."""


class ExtractionError(ResearchAnalyserError):
    """MonkeyOCR extraction failure."""


class DiagramError(ResearchAnalyserError):
    """PaperBanana diagram generation failure."""


class ReviewError(ResearchAnalyserError):
    """Agentic reviewer failure."""


class ConfigError(ResearchAnalyserError):
    """Configuration error."""
