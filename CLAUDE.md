# Research Analyser - Project Guide

## Project Overview
AI-powered research paper analysis tool combining MonkeyOCR 1.5, PaperBanana, Stanford Agentic Reviewer, Qwen3-TTS, and STORM Wikipedia-style reporting.

## Key Files
- `research_analyser/analyser.py` - Main orchestrator
- `research_analyser/models.py` - All data models
- `research_analyser/ocr_engine.py` - MonkeyOCR integration
- `research_analyser/diagram_generator.py` - PaperBanana integration
- `research_analyser/reviewer.py` - Agentic review (LangGraph)
- `research_analyser/storm_reporter.py` - STORM Wikipedia-style report
- `research_analyser/tts_engine.py` - Qwen3-TTS audio narration
- `research_analyser/comparison.py` - Score comparison utility
- `research_analyser/report_generator.py` - Output assembly
- `packaging/macos_launcher.py` - macOS .app launcher (pywebview + Streamlit)
- `scripts/build_macos_dmg.sh` - PyInstaller DMG build script
- `SPEC.md` - Full specification document (source of truth)
- `docs/key_points_and_equations.md` - Formulae reference

## Key Formula
Review score: `score = -0.3057 + 0.7134*S + 0.4242*P + 1.0588*C`
Where S=Soundness, P=Presentation, C=Contribution (each 1-4 scale)

## Commands
- CLI: `python -m research_analyser analyse <source>`
- Web UI: `streamlit run app.py`
- API: `uvicorn research_analyser.api:app`
- Tests: `pytest tests/`
- Build macOS DMG: `./scripts/build_macos_dmg.sh`

## Git Commits
- Author is always `kp-algomaster <kp-algomaster@users.noreply.github.com>`
- NEVER add `Co-Authored-By` trailer lines to commit messages
- Write commit messages without any AI attribution

## Git Push — GitHub PAT
The GitHub Personal Access Token is stored as `GITHUB_PAT` in `.env`.
When pushing to GitHub, ALWAYS use this pattern (inject token, push, restore clean URL):
```bash
GITHUB_PAT=$(grep '^GITHUB_PAT=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
git remote set-url origin "https://kp-algomaster:${GITHUB_PAT}@github.com/kp-algomaster/Research_Analyser.git"
git push origin main
git remote set-url origin https://github.com/kp-algomaster/Research_Analyser.git
```
Never commit `.env` or embed the PAT value directly in any file or command output.

## macOS Bundle Notes
- Output dir in bundled .app → `~/ResearchAnalyserOutput/` (read-only bundle workaround)
- Launcher logs → `~/ResearchAnalyserOutput/launcher.log`
- `signal.signal()` is monkey-patched in the Streamlit thread (main thread owned by pywebview)
- Always delete `__pycache__` before building to avoid stale `.pyc` in bundle

## Dependencies
- MonkeyOCR: github.com/Yuliang-Liu/MonkeyOCR
- PaperBanana: github.com/llmsresearch/paperbanana
- Agentic Review: github.com/debashis1983/agentic-paper-review
- Qwen3-TTS: huggingface.co/Qwen/Qwen3-TTS
- STORM: pypi.org/project/knowledge-storm
