# Research Analyser - Project Guide

## Project Overview
AI-powered research paper analysis tool combining MonkeyOCR 1.5, PaperBanana, and Stanford Agentic Reviewer.

## Key Files
- `research_analyser/analyser.py` - Main orchestrator
- `research_analyser/models.py` - All data models
- `research_analyser/ocr_engine.py` - MonkeyOCR integration
- `research_analyser/diagram_generator.py` - PaperBanana integration
- `research_analyser/reviewer.py` - Agentic review (LangGraph)
- `research_analyser/report_generator.py` - Output assembly
- `SPEC.md` - Full specification document
- `docs/key_points_and_equations.md` - Formulae reference

## Key Formula
Review score: `score = -0.3057 + 0.7134*S + 0.4242*P + 1.0588*C`
Where S=Soundness, P=Presentation, C=Contribution (each 1-4 scale)

## Commands
- CLI: `python -m research_analyser analyse <source>`
- Web UI: `streamlit run app.py`
- API: `uvicorn research_analyser.api:app`
- Tests: `pytest tests/`

## Dependencies
- MonkeyOCR: github.com/Yuliang-Liu/MonkeyOCR
- PaperBanana: github.com/llmsresearch/paperbanana
- Agentic Review: github.com/debashis1983/agentic-paper-review
