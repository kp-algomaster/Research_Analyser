# Research Analyser

An AI-powered research paper analysis tool that combines **MonkeyOCR 1.5** for PDF extraction, **PaperBanana** for diagram generation, and **Stanford Agentic Reviewer** for peer-review-quality analysis.

## Features

- **PDF Upload & URL Input** - Upload PDFs or paste paper URLs (arXiv, Semantic Scholar, DOI links)
- **Intelligent OCR Extraction** - MonkeyOCR 1.5 extracts text, equations (LaTeX), tables, and figures with state-of-the-art accuracy
- **AI Diagram Generation** - PaperBanana generates methodology diagrams, architecture overviews, and statistical plots
- **Agentic Paper Review** - Stanford-style multi-dimensional scoring (Soundness, Presentation, Contribution)
- **Structured Analysis Reports** - Markdown reports with key findings, equations, strengths/weaknesses, and visual summaries
- **Spec-Driven Output** - Machine-readable `.md` files for downstream code generation or integration

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
│ PDF      │ Text/LaTeX   │ Agentic       │ Key Points    │
│ Upload   │ Extraction   │ Reviewer      │ & Equations   │
├──────────┼──────────────┼───────────────┼───────────────┤
│ arXiv    │ Table/Figure │ Summary       │ Diagrams      │
│ Resolver │ Detection    │ Generator     │ (PNG/SVG)     │
└──────────┴──────────────┴───────────────┴───────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- CUDA-compatible GPU (for MonkeyOCR) or CPU fallback mode
- API keys for PaperBanana diagram generation (OpenAI or Google Gemini)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Research_Analyser.git
cd Research_Analyser

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install MonkeyOCR
pip install monkeyocr

# Install PaperBanana
pip install paperbanana

# Install Agentic Reviewer dependencies
pip install langgraph langchain-openai tavily-python

# Download MonkeyOCR model weights
python -m monkeyocr.download --model MonkeyOCR-pro-3B

# Configure environment
cp .env.example .env
# Edit .env with your API keys
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

## Usage Examples

### CLI

```bash
# Analyse a local PDF
python -m research_analyser analyse paper.pdf --output ./reports/

# Analyse from URL
python -m research_analyser analyse https://arxiv.org/abs/2401.12345 --diagrams --review

# Generate only diagrams
python -m research_analyser diagrams paper.pdf --type methodology

# Generate only review
python -m research_analyser review paper.pdf --venue "ICLR 2026"
```

### Python API

```python
from research_analyser import ResearchAnalyser

analyser = ResearchAnalyser()
report = analyser.analyse("paper.pdf", generate_diagrams=True, generate_review=True)

print(report.summary)
print(report.key_equations)
report.save("./output/")
```

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
