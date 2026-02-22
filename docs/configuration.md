# Configuration Guide

## Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

### Required Keys

| Variable | Description | Where to get |
|----------|-------------|--------------|
| `OPENAI_API_KEY` | OpenAI API key (for reviewer LLM) | [platform.openai.com](https://platform.openai.com/api-keys) |

### Diagram Generation (choose one)

| Variable | Description | Where to get |
|----------|-------------|--------------|
| `GOOGLE_API_KEY` | Google Gemini API key (free tier) | [ai.google.dev](https://ai.google.dev/) |
| `OPENAI_API_KEY` | Also works for OpenAI image generation | Same as above |

### Optional Keys

| Variable | Description | Where to get |
|----------|-------------|--------------|
| `TAVILY_API_KEY` | Enhanced related work search | [tavily.com](https://tavily.com/) |
| `SEMANTIC_SCHOLAR_API_KEY` | Higher rate limits | [semanticscholar.org](https://www.semanticscholar.org/product/api) |
| `HF_TOKEN` | HuggingFace token (model downloads) | [huggingface.co](https://huggingface.co/settings/tokens) |

## Configuration File

The `config.yaml` file controls all pipeline settings:

### OCR Settings

```yaml
ocr:
  model: "MonkeyOCR-pro-3B"    # Model variant
  device: "auto"                 # "cuda", "cpu", or "auto"
  page_split: true               # Split pages for processing
  output_format: "markdown"      # Output format
```

**Model options:**
- `MonkeyOCR-pro-3B` - Best accuracy, ~1 page/sec on RTX 4090
- `MonkeyOCR-pro-1.2B` - 36% faster, slightly less accurate

### Diagram Settings

```yaml
diagrams:
  provider: "google"              # "openai", "google", "openrouter"
  vlm_model: "gemini-2.0-flash"  # Vision-language model
  image_model: "gemini-3-pro-image-preview"  # Image generation model
  optimize_inputs: true           # Enable Phase 0 preprocessing
  auto_refine: true               # Enable iterative refinement
  max_iterations: 3               # Refinement rounds
  output_format: "png"            # "png", "svg", "pdf", "webp"
  resolution: "2k"                # "2k" or "4k"
```

### Review Settings

```yaml
review:
  llm_provider: "openai"
  model: "gpt-4o"
  use_tavily: true                # Enhanced related work search
  scoring_weights:
    soundness: 0.7134             # Technical correctness (32.5%)
    presentation: 0.4242          # Writing clarity (19.3%)
    contribution: 1.0588          # Significance/novelty (48.2%)
  intercept: -0.3057
```

## Hardware Requirements

### MonkeyOCR GPU Requirements

| GPU | VRAM | Speed (3B) | Speed (1.2B) |
|-----|------|-----------|-------------|
| RTX 4090 | 24GB | 1.01 pg/s | 1.44 pg/s |
| RTX 3090 | 24GB | 0.50 pg/s | 0.68 pg/s |
| RTX 4060 | 8GB | Quantized | Quantized |
| CPU | - | Slow | Slow |

### CPU Fallback

Set `device: "cpu"` in config for systems without CUDA GPUs.
Processing will be significantly slower but functional.
