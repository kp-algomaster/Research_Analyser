from __future__ import annotations

import json
from pathlib import Path

import fitz


class MonkeyOCR:
    def __init__(self, model_name: str = "MonkeyOCR-pro-3B", device: str = "auto"):
        self.model_name = model_name
        self.device = device

    def parse(self, pdf_path: str, output_dir: str) -> None:
        source = Path(pdf_path)
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)

        markdown_chunks: list[str] = []
        with fitz.open(source) as document:
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if text:
                    markdown_chunks.append(f"## Page {page_number}\n\n{text}\n")

        markdown_content = "\n".join(markdown_chunks).strip() or "# Untitled\n"
        stem = source.stem

        markdown_path = destination / f"{stem}.md"
        blocks_path = destination / f"{stem}_middle.json"

        markdown_path.write_text(markdown_content, encoding="utf-8")
        blocks_path.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")