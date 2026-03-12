# Changelog

## 0.7.1 — 2026-03-12

### Fixed
- **Start Server on existing venv** — subsequent "Start Server" calls now run `pip install --quiet -r requirements.txt` before launching uvicorn, ensuring packages added after the venv was created (e.g. `sse-starlette`) are always present. This fixes the `501 Not Implemented` error on `/analyse/stream`.

## 0.7.0 — 2026-03-12

## 0.6.0 — 2026-03-03

### Added
- **Apple Silicon auto-detection** — device info endpoint detects Apple M-series chips, NVIDIA CUDA, or CPU-only and recommends the optimal MonkeyOCR variant.
- **Apple Silicon MonkeyOCR (MLX)** — one-click setup of the MLX-VLM-accelerated OCR backend for ~3× faster processing on Apple Silicon Macs.
- **SSL bypass for corporate firewalls** — setup subprocesses (uv, git, pip) now honour `SKIP_SSL_VERIFICATION` to traverse TLS-intercepting proxies.
- **Device & variant info in sidebar** — MonkeyOCR status shows detected device type and installed variant.
- **Graceful setup recovery** — if `setup.sh` exits non-zero but the install is usable (e.g. model-download SSL failures), the extension still reports success.

## 0.5.0 — 2026-03-02

### Added
- Initial Marketplace release.
- Paper analysis via arXiv ID, URL, DOI, or local PDF.
- MonkeyOCR download, delete, and re-download management with sidebar progress spinner.
- Beautiful Mermaid diagram generation.
- Equation hover cards and insert-at-cursor.
- Spec preview with offline KaTeX rendering.
- Configurable API keys (Google AI, HuggingFace) via VS Code settings.
