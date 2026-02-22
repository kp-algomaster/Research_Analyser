# Research Analyser

An AI-powered research paper analysis tool that combines **MonkeyOCR 1.5** for PDF extraction, **PaperBanana** for publication-quality diagram generation, **LangGraph Agentic Reviewer** for peer-review-quality analysis, and **PaperReview.ai** comparison for external review benchmarking.

## Features

- **PDF Upload & URL Input** — Upload PDFs or paste paper URLs (arXiv, Semantic Scholar, DOI links)
- **Intelligent OCR Extraction** — MonkeyOCR 1.5 extracts text, equations (LaTeX), tables, and figures with state-of-the-art accuracy
- **AI Diagram Generation** — PaperBanana generates methodology diagrams, architecture overviews, and results plots using Gemini VLM + Imagen
- **Agentic Paper Review** — LangGraph 9-node workflow with ML-calibrated scoring (Soundness, Presentation, Contribution)
- **PaperReview.ai Comparison** — Upload external review JSON from [PaperReview.ai](https://paperreview.ai) to compare scores against local review
- **Configurable API Keys** — Sidebar settings for Google (PaperBanana), OpenAI (Reviewer), and Tavily (Related Work Search) keys
- **Structured Reports** — Markdown + HTML reports with key findings, equations, strengths/weaknesses, and visual summaries
- **macOS DMG App** — Standalone desktop app bundled with PyInstaller

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Research Analyser                      │
├──────────┬──────────────┬───────────────┬───────────────┤
│  Input   │   Extraction │   Analysis    │    Output     │
│  Layer   │   Pipeline   │   Pipeline    │    Layer      │
├──────────┼──────────────┼───────────────┼───────────────┤
│ URL      │ MonkeyOCR    │ PaperBanana   │ Markdown      │
│ Fetcher  │ 1.5          │ Diagrams      │ Report        │
├──────────┼──────────────┼───────────────┼───────────────┤
│ PDF      │ Text/LaTeX   │ LangGraph     │ Key Points    │
│ Upload   │ Extraction   │ Reviewer      │ & Equations   │
├──────────┼──────────────┼───────────────┼───────────────┤
│ arXiv    │ Table/Figure │ PaperReview   │ Diagrams      │
│ Resolver │ Detection    │ Comparison    │ (PNG/SVG)     │
└──────────┴──────────────┴───────────────┴───────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12 (recommended; 3.10+ supported)
- CUDA-compatible GPU (for MonkeyOCR) or CPU fallback mode
- API keys: Google Gemini (diagrams), OpenAI (review), Tavily (optional, related work search)

### Installation

```bash
# Clone the repository
git clone https://github.com/kp-algomaster/Research_Analyser.git
cd Research_Analyser

# Create virtual environment (Python 3.12 recommended)
python3.12 -m venv .venv312
source .venv312/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install MonkeyOCR and PaperBanana
pip install monkeyocr paperbanana

# Download MonkeyOCR model weights
python -m monkeyocr.download --model MonkeyOCR-pro-3B

# Configure environment
cp .env.example .env
# Edit .env with your API keys (GOOGLE_API_KEY, OPENAI_API_KEY, etc.)
```

### Run the Application

```bash
# CLI mode
python -m research_analyser analyse paper.pdf
python -m research_analyser analyse https://arxiv.org/abs/2401.12345

# Web UI mode (Streamlit)
streamlit run app.py

# API server mode
uvicorn research_analyser.api:app --host 0.0.0.0 --port 8000
```

### Build macOS DMG

```bash
./scripts/build_macos_dmg.sh
# Output: dist/ResearchAnalyser.dmg
```

## Usage Examples

### CLI

```bash
# Analyse with diagrams and review
python -m research_analyser analyse https://arxiv.org/abs/2602.17002

# Diagrams only (no review)
python -m research_analyser analyse paper.pdf --diagrams --no-review -d methodology

# Review only (no diagrams)
python -m research_analyser analyse paper.pdf --no-diagrams --review
```

### Web UI

The Streamlit UI provides:
- **Sidebar** — Configure API keys (Google, OpenAI, Tavily), diagram types, provider, and venue
- **Analysis** — Upload PDF or enter arXiv URL, click "Analyse Paper"
- **PaperReview.ai Comparison** — Upload a review JSON from paperreview.ai to compare scores

### Python API

```python
import asyncio
from research_analyser.analyser import ResearchAnalyser
from research_analyser.models import AnalysisOptions

analyser = ResearchAnalyser()
options = AnalysisOptions(generate_diagrams=True, generate_review=True)
report = asyncio.run(analyser.analyse("https://arxiv.org/abs/2602.17002", options=options))

print(report.summary.one_sentence)
print(f"Review score: {report.review.overall_score:.1f}/10")
```

### PaperReview.ai Comparison

Upload external review JSON with this format:
```json
{
  "overall_score": 6.9,
  "soundness": 3.1,
  "presentation": 3.0,
  "contribution": 3.2,
  "confidence": 3.5
}
```

## Review Scoring Formula

$$\text{score} = -0.3057 + 0.7134 \times S + 0.4242 \times P + 1.0588 \times C$$

Where $S$ = Soundness, $P$ = Presentation, $C$ = Contribution (each on 1–4 scale). Output maps to 1–10 overall score.

## Output Structure

```
output/
├── report.md                    # Full analysis report
├── key_points.md                # Extracted key points & equations
├── review.md                    # Peer review analysis
├── diagrams/
│   ├── methodology.png          # Methodology overview diagram
│   ├── architecture.png         # Architecture diagram
│   └── results_plot.png         # Results visualization
├── extracted/
│   ├── full_text.md             # Complete extracted text
│   ├── equations.json           # All equations in LaTeX
│   ├── tables.json              # Extracted tables
│   └── figures/                 # Extracted figures
└── metadata.json                # Paper metadata & analysis config
```

## Configuration

See [docs/configuration.md](docs/configuration.md) for full configuration options.

## GitHub Repositories (Dependencies)

| Tool | Repository | Purpose |
|------|-----------|---------|
| MonkeyOCR 1.5 | [Yuliang-Liu/MonkeyOCR](https://github.com/Yuliang-Liu/MonkeyOCR) | PDF/document content extraction |
| PaperBanana | [llmsresearch/paperbanana](https://github.com/llmsresearch/paperbanana) | AI diagram generation |
| PaperBanana (Official) | [dwzhu-pku/PaperBanana](https://github.com/dwzhu-pku/PaperBanana) | Original research implementation |
| Agentic Paper Review | [debashis1983/agentic-paper-review](https://github.com/debashis1983/agentic-paper-review) | Open-source paper reviewer |
| PaperReview.ai | [paperreview.ai](https://paperreview.ai/) | Stanford Agentic Reviewer (web) |

## License

MIT License - see [LICENSE](LICENSE) for details.
