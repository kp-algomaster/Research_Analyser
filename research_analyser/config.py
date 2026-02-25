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
    skip_ssl_verification: bool = False


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


class StormConfig(BaseModel):
    enabled: bool = False
    conv_model: str = "gpt-4o-mini"
    outline_model: str = "gpt-4o"
    article_model: str = "gpt-4o"
    max_conv_turn: int = Field(default=3, ge=1)
    max_perspective: int = Field(default=3, ge=1)
    search_top_k: int = Field(default=5, ge=1)
    retrieve_top_k: int = Field(default=5, ge=1)


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
    storm: StormConfig = Field(default_factory=StormConfig)
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

    model_config = {
        "env_prefix": "RESEARCH_ANALYSER_",
        "env_nested_delimiter": "__",
        "extra": "ignore",  # tolerate unknown yaml keys (e.g. from newer config.yaml)
    }

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

        skip_ssl_env = str(os.getenv("SKIP_SSL_VERIFICATION", "")).strip().lower()
        if skip_ssl_env in {"1", "true", "yes", "on"}:
            diagrams = file_config.setdefault("diagrams", {})
            diagrams["skip_ssl_verification"] = True

        return cls(**file_config)
