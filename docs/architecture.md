# Architecture Overview

## System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      Research Analyser                         │
│                                                                │
│  ┌──────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐ │
│  │  Input    │    │ Extraction│    │ Analysis  │    │ Output │ │
│  │  Handler  │───▶│ (OCR)     │───▶│ Pipeline  │───▶│ Layer  │ │
│  └──────────┘    └───────────┘    └───────────┘    └────────┘ │
│       │               │               │    │            │      │
│   ┌───┴───┐     ┌─────┴─────┐   ┌────┴┐ ┌┴─────┐  ┌──┴───┐  │
│   │URL    │     │MonkeyOCR  │   │Paper│ │Agentic│  │Report│  │
│   │arXiv  │     │1.5        │   │Banana│ │Review │  │Gen   │  │
│   │DOI    │     │pro-3B     │   │     │ │       │  │      │  │
│   │PDF    │     │           │   │     │ │       │  │      │  │
│   └───────┘     └───────────┘   └─────┘ └───────┘  └──────┘  │
└────────────────────────────────────────────────────────────────┘
```

## Module Dependency Graph

```
research_analyser/
├── __init__.py          # Public API exports
├── __main__.py          # CLI entry point (click)
├── analyser.py          # Main orchestrator
├── config.py            # Configuration management
├── exceptions.py        # Custom exceptions
├── models.py            # Data models (dataclasses)
├── input_handler.py     # PDF resolution (URL, arXiv, DOI)
├── ocr_engine.py        # MonkeyOCR 1.5 wrapper
├── diagram_generator.py # PaperBanana wrapper
├── reviewer.py          # Agentic review (LangGraph)
├── report_generator.py  # Output assembly
└── api.py               # FastAPI REST API
```

## Data Flow

```
1. INPUT RESOLUTION
   source (str) → InputHandler.resolve() → Path (local PDF)

2. CONTENT EXTRACTION
   Path (PDF) → OCREngine.extract() → ExtractedContent
                                        ├── full_text (markdown)
                                        ├── equations (LaTeX)
                                        ├── tables
                                        ├── figures
                                        └── sections

3. PARALLEL ANALYSIS
   ExtractedContent ──┬──→ DiagramGenerator.generate() → list[GeneratedDiagram]
                      └──→ PaperReviewer.review()      → PeerReview

4. REPORT ASSEMBLY
   All results → ReportGenerator.save_all() → output/
                                               ├── report.md
                                               ├── key_points.md
                                               ├── spec_output.md
                                               ├── review.md
                                               ├── metadata.json
                                               ├── diagrams/
                                               └── extracted/
```

## External Dependencies

### MonkeyOCR 1.5
- **Repo:** github.com/Yuliang-Liu/MonkeyOCR
- **Model:** 3B parameter multimodal LLM
- **Architecture:** Structure-Recognition-Relation (SRR) triplet paradigm
- **Output:** Markdown + layout PDF + JSON blocks

### PaperBanana
- **Repo:** github.com/llmsresearch/paperbanana
- **Pipeline:** 5-agent system (Retriever → Planner → Stylist → Visualizer → Critic)
- **Output:** Publication-quality PNG/SVG diagrams

### Agentic Paper Review
- **Based on:** github.com/debashis1983/agentic-paper-review
- **Pipeline:** 9-node LangGraph workflow
- **Scoring:** ML-calibrated linear regression trained on 46,748 ICLR reviews

## Interfaces

### CLI
```bash
python -m research_analyser analyse <source>
python -m research_analyser diagrams <source>
python -m research_analyser review <source>
```

### Python API
```python
from research_analyser import ResearchAnalyser
analyser = ResearchAnalyser()
report = await analyser.analyse("paper.pdf")
```

### REST API
```
POST /api/v1/analyse     # Submit paper
GET  /api/v1/analyse/:id # Get results
POST /api/v1/extract     # Extract only
GET  /api/v1/health      # Health check
```

### Streamlit UI
```bash
streamlit run app.py
```
