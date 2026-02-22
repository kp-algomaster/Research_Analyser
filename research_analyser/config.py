"""Configuration management for Research Analyser."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class OCRConfig(BaseModel):
    model: str = "MonkeyOCR-pro-3B"
    device: str = "auto"
    page_split: bool = True
    output_format: str = "markdown"


class DiagramConfig(BaseModel):
    provider: str = "gemini"
    vlm_model: str = "gemini-2.0-flash"
    image_model: str = "gemini-3-pro-image-preview"
    optimize_inputs: bool = True
    auto_refine: bool = True
    max_iterations: int = 3
    output_format: str = "png"
    resolution: str = "2k"


class TTSConfig(BaseModel):
    enabled: bool = False
    model: str = "Qwen/Qwen3-TTS"
    device: str = "auto"
    speaker: str = "default"


class ReviewScoringWeights(BaseModel):
    soundness: float = 0.7134
    presentation: float = 0.4242
    contribution: float = 1.0588


class ReviewConfig(BaseModel):
    llm_provider: str = "openai"
    model: str = "gpt-4o"
    use_tavily: bool = True
    scoring_weights: ReviewScoringWeights = Field(default_factory=ReviewScoringWeights)
    intercept: float = -0.3057


class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    max_upload_size_mb: int = 100
    job_timeout_seconds: int = 600


class AppConfig(BaseModel):
    name: str = "Research Analyser"
    output_dir: str = "./output"
    temp_dir: str = "./tmp"
    log_level: str = "INFO"


class Config(BaseSettings):
    """Application configuration loaded from env vars and config file."""

    app: AppConfig = Field(default_factory=AppConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    diagrams: DiagramConfig = Field(default_factory=DiagramConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    # API Keys (from environment)
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    semantic_scholar_api_key: Optional[str] = Field(
        default=None, alias="SEMANTIC_SCHOLAR_API_KEY"
    )
    hf_token: Optional[str] = Field(default=None, alias="HF_TOKEN")

    model_config = {"env_prefix": "RESEARCH_ANALYSER_", "env_nested_delimiter": "__"}

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> Config:
        """Load configuration from YAML file and environment variables."""
        config_path = config_path or os.getenv(
            "RESEARCH_ANALYSER_CONFIG", "./config.yaml"
        )

        file_config = {}
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file) as f:
                file_config = yaml.safe_load(f) or {}

        return cls(**file_config)
