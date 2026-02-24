"""OCR extraction engine using MonkeyOCR 1.5."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

from research_analyser.exceptions import ExtractionError
from research_analyser.models import (
    Equation,
    ExtractedContent,
    Figure,
    Reference,
    Section,
    Table,
)

logger = logging.getLogger(__name__)

# Equation detection patterns
DISPLAY_EQUATION_PATTERNS = [
    re.compile(r"\$\$(.+?)\$\$", re.DOTALL),
    re.compile(r"\\\[(.+?)\\\]", re.DOTALL),
    re.compile(r"\\begin\{equation\}(.+?)\\end\{equation\}", re.DOTALL),
    re.compile(r"\\begin\{align\}(.+?)\\end\{align\}", re.DOTALL),
    re.compile(r"\\begin\{gather\}(.+?)\\end\{gather\}", re.DOTALL),
]

INLINE_EQUATION_PATTERN = re.compile(
    r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)"
)

EQUATION_LABEL_PATTERN = re.compile(r"\\label\{(eq:[^}]+)\}")

# Section header pattern (markdown)
SECTION_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
LATEX_SECTION_PATTERN = re.compile(
    r"\\(?:sub)*section\*?\{([^}]+)\}",
    re.MULTILINE,
)


class OCREngine:
    """Extract structured content from PDF using MonkeyOCR 1.5."""

    def __init__(self, model_name: str = "MonkeyOCR-pro-3B", device: str = "auto"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        """Lazy-load the MonkeyOCR model."""
        if self._model is not None:
            return

        try:
            from monkeyocr import MonkeyOCR

            self._model = MonkeyOCR(model_name=self.model_name, device=self.device)
            logger.info(f"Loaded MonkeyOCR model: {self.model_name}")
        except ImportError:
            raise ExtractionError(
                "MonkeyOCR is not installed. Install with: pip install monkeyocr"
            )
        except Exception as e:
            raise ExtractionError(f"Failed to load MonkeyOCR model: {e}")

    async def extract(self, pdf_path: Path) -> ExtractedContent:
        """Full extraction pipeline.

        1. Load PDF, run MonkeyOCR parse
        2. Merge page results into unified document
        3. Post-process: equation detection, table parsing, figure extraction
        4. Build structured ExtractedContent
        """
        self._load_model()

        try:
            # Run MonkeyOCR parse
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_dir = Path(tmp_dir)
                self._model.parse(str(pdf_path), output_dir=str(output_dir))

                # Read outputs
                stem = pdf_path.stem
                markdown_path = output_dir / f"{stem}.md"
                blocks_path = output_dir / f"{stem}_middle.json"

                markdown_text = ""
                if markdown_path.exists():
                    markdown_text = markdown_path.read_text(encoding="utf-8")

                blocks = []
                if blocks_path.exists():
                    blocks = json.loads(blocks_path.read_text(encoding="utf-8"))

        except Exception as e:
            raise ExtractionError(f"MonkeyOCR extraction failed: {e}")

        # Post-process extracted content
        sections = self.parse_sections(markdown_text)
        equations = self.extract_equations(markdown_text)
        tex_source_path = pdf_path.with_suffix(".source.tex")
        if tex_source_path.exists():
            try:
                tex_source_text = tex_source_path.read_text(encoding="utf-8")
                tex_equations = self.extract_equations(tex_source_text)
                if tex_equations:
                    for index, equation in enumerate(tex_equations, start=len(equations) + 1):
                        equation.id = f"eq_{index:03d}"
                    equations.extend(tex_equations)
                    logger.info(f"Added {len(tex_equations)} equations from arXiv source TeX")
            except Exception as e:
                logger.warning(f"Failed to parse TeX source equations from {tex_source_path}: {e}")

        tables = self.extract_tables(blocks, markdown_text)
        figures = self.extract_figures(blocks, markdown_text)
        title = self._extract_title(markdown_text, sections)
        authors = self._extract_authors(markdown_text)
        abstract = self._extract_abstract(markdown_text, sections)
        references = self._extract_references(markdown_text)

        metadata_path = pdf_path.with_suffix(".meta.json")
        if metadata_path.exists():
            try:
                source_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if source_metadata.get("title"):
                    title = source_metadata["title"]
                if source_metadata.get("authors"):
                    authors = source_metadata["authors"]
                if source_metadata.get("abstract"):
                    abstract = source_metadata["abstract"]
            except Exception as e:
                logger.warning(f"Failed to load source metadata from {metadata_path}: {e}")

        return ExtractedContent(
            full_text=markdown_text,
            title=title,
            authors=authors,
            abstract=abstract,
            sections=sections,
            equations=equations,
            tables=tables,
            figures=figures,
            references=references,
            metadata={
                "source_file": str(pdf_path),
                "ocr_model": self.model_name,
                "num_equations": len(equations),
                "num_tables": len(tables),
                "num_figures": len(figures),
            },
        )

    def extract_equations(self, markdown_text: str) -> list[Equation]:
        """Parse LaTeX equations from MonkeyOCR markdown output."""
        equations = []
        eq_counter = 0

        # Extract display equations
        for pattern in DISPLAY_EQUATION_PATTERNS:
            for match in pattern.finditer(markdown_text):
                eq_counter += 1
                latex = match.group(1).strip()

                # Find surrounding context (50 chars before/after)
                start = max(0, match.start() - 100)
                end = min(len(markdown_text), match.end() + 100)
                context = markdown_text[start:end].strip()

                # Check for label
                label_match = EQUATION_LABEL_PATTERN.search(latex)
                label = label_match.group(1) if label_match else None

                # Determine which section this equation belongs to
                section = self._find_containing_section(markdown_text, match.start())

                equations.append(
                    Equation(
                        id=f"eq_{eq_counter:03d}",
                        latex=latex,
                        context=context,
                        section=section,
                        is_inline=False,
                        label=label,
                        description=self._describe_equation_relevance(
                            latex=latex,
                            section=section,
                        ),
                    )
                )

        # Extract inline equations
        for match in INLINE_EQUATION_PATTERN.finditer(markdown_text):
            eq_counter += 1
            latex = match.group(1).strip()

            # Skip very short matches (likely false positives like currency)
            if len(latex) < 3:
                continue

            start = max(0, match.start() - 100)
            end = min(len(markdown_text), match.end() + 100)
            context = markdown_text[start:end].strip()
            section = self._find_containing_section(markdown_text, match.start())

            equations.append(
                Equation(
                    id=f"eq_{eq_counter:03d}",
                    latex=latex,
                    context=context,
                    section=section,
                    is_inline=True,
                    description=self._describe_equation_relevance(
                        latex=latex,
                        section=section,
                    ),
                )
            )

        return equations

    def extract_tables(self, blocks: list[dict], markdown_text: str = "") -> list[Table]:
        """Extract tables from MonkeyOCR block output.

        Falls back to markdown pipe-table detection when the blocks JSON is
        unavailable or contains no table entries.
        """
        tables = []
        table_counter = 0

        for block in blocks:
            if block.get("type") in ("table", "table_body", "table_caption"):
                table_counter += 1
                tables.append(
                    Table(
                        id=f"table_{table_counter:03d}",
                        content=block.get("content", ""),
                        caption=block.get("caption"),
                        section=block.get("section", ""),
                    )
                )

        # Fallback: detect markdown pipe tables when block output is empty
        if not tables and markdown_text:
            tables = self._extract_tables_from_markdown(markdown_text)

        return tables

    def _extract_tables_from_markdown(self, text: str) -> list[Table]:
        """Detect markdown pipe-formatted tables in OCR output."""
        tables: list[Table] = []
        table_counter = 0
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if "|" in line and line.strip().startswith("|"):
                # Collect contiguous table rows
                table_lines = []
                while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                # Must have header + separator + at least one data row
                if len(table_lines) >= 3 and re.match(r"^\s*\|[\s\-\|:]+\|\s*$", table_lines[1]):
                    table_counter += 1
                    col_count = table_lines[0].count("|") - 1
                    row_count = len(table_lines) - 2  # header + separator excluded
                    # Look for a Table caption just before or after
                    caption = None
                    if i < len(lines):
                        cap_match = re.match(
                            r"^\*?\*?(?:Table|Tab\.?)\s*\d+[.:]\*?\*?\s*(.+)",
                            lines[i].strip(), re.IGNORECASE,
                        )
                        if cap_match:
                            caption = cap_match.group(1)
                    tables.append(
                        Table(
                            id=f"table_{table_counter:03d}",
                            content="\n".join(table_lines),
                            caption=caption,
                            rows=row_count,
                            cols=col_count,
                        )
                    )
            else:
                i += 1
        return tables

    def extract_figures(self, blocks: list[dict], markdown_text: str = "") -> list[Figure]:
        """Extract figures from MonkeyOCR block output.

        Falls back to caption-pattern scanning when the blocks JSON is
        unavailable or contains no figure entries.
        """
        figures = []
        fig_counter = 0

        for block in blocks:
            if block.get("type") in ("figure", "figure_caption", "image"):
                fig_counter += 1
                figures.append(
                    Figure(
                        id=f"fig_{fig_counter:03d}",
                        image_path=block.get("image_path"),
                        caption=block.get("caption"),
                        section=block.get("section", ""),
                        page=block.get("page", 0),
                    )
                )

        # Fallback: find Figure N captions in the markdown text
        if not figures and markdown_text:
            figures = self._extract_figures_from_markdown(markdown_text)

        return figures

    def _extract_figures_from_markdown(self, text: str) -> list[Figure]:
        """Detect figures by scanning for 'Figure N' / 'Fig. N' caption lines."""
        figures: list[Figure] = []
        fig_counter = 0
        caption_pattern = re.compile(
            r"(?:^|\n)\s*\*?\*?(?:Figure|Fig\.?)\s*(\d+)\*?\*?[.:\-]?\s*(.{5,200})",
            re.IGNORECASE,
        )
        for m in caption_pattern.finditer(text):
            caption_text = m.group(2).strip().rstrip("*")
            fig_counter += 1
            figures.append(
                Figure(
                    id=f"fig_{fig_counter:03d}",
                    caption=caption_text,
                )
            )
        return figures

    def parse_sections(self, markdown_text: str) -> list[Section]:
        """Parse document into hierarchical sections from markdown headers."""
        sections = []
        matches = list(SECTION_HEADER_PATTERN.finditer(markdown_text))

        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()

            # Get content between this header and the next
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
            content = markdown_text[start:end].strip()

            sections.append(
                Section(title=title, level=level, content=content)
            )

        return sections

    def _find_containing_section(self, text: str, position: int) -> str:
        """Find which section contains a given text position."""
        section_markers: list[tuple[int, str]] = []

        for match in SECTION_HEADER_PATTERN.finditer(text):
            section_markers.append((match.start(), match.group(2).strip()))

        for match in LATEX_SECTION_PATTERN.finditer(text):
            section_markers.append((match.start(), match.group(1).strip()))

        section_markers.sort(key=lambda marker: marker[0])

        last_section = "Preamble"
        for marker_position, marker_title in section_markers:
            if marker_position > position:
                break
            last_section = marker_title

        return last_section

    def _describe_equation_relevance(self, latex: str, section: str) -> str:
        """Generate concise relevance and potential-use explanation."""
        lower = latex.lower()

        if any(token in lower for token in ["\\int", "\\sum", "\\prod"]):
            role = "aggregates contributions across components"
            example = "computing total system energy or accumulated force over elements"
        elif any(token in lower for token in ["\\dot", "\\ddot", "\\partial", "d/"]):
            role = "captures dynamic rate-of-change behavior"
            example = "updating velocities/accelerations during time integration"
        elif any(token in lower for token in ["=", "\\mathbf", "\\mathbf{r}", "\\mathbf{n}"]):
            role = "defines a core state or transformation relationship"
            example = "mapping element coordinates to world coordinates in simulation"
        else:
            role = "formalizes a mathematical relationship used by the method"
            example = "implementing the same formula in a numerical solver"

        return (
            f"Relevance: In section '{section}', this equation {role}. "
            f"Potential use: {example}."
        )

    def _extract_title(self, text: str, sections: list[Section]) -> str:
        """Extract paper title from the first H1 or first line."""
        for section in sections:
            if section.level == 1:
                return section.title

        lines = text.strip().split("\n")
        if lines:
            return lines[0].strip("# ").strip()
        return "Untitled"

    def _extract_authors(self, text: str) -> list[str]:
        """Extract author names (heuristic-based)."""
        lines = text.strip().split("\n")
        # Authors are typically in the first few lines after the title
        for line in lines[1:5]:
            line = line.strip()
            if line and not line.startswith("#") and "," in line:
                return [a.strip() for a in line.split(",")]
        return []

    def _extract_abstract(self, text: str, sections: list[Section]) -> str:
        """Extract abstract section."""
        for section in sections:
            if "abstract" in section.title.lower():
                return section.content

        abstract_match = re.search(
            r"\babstract\b[:\s]*(.+?)(?:\n\s*\n|\n#|\n##|\n1\.|\nI\.)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if abstract_match:
            return abstract_match.group(1).strip()
        return ""

    def _extract_references(self, text: str) -> list[Reference]:
        """Extract references supporting multiple citation formats.

        Handled formats:
          [1] Author, Title...          (IEEE / ACL style)
          1. Author, Title...           (numbered list style)
          Author et al. (Year). Title   (APA / NeurIPS style, author-year)
        """
        references: list[Reference] = []
        ref_section = False
        ref_counter = 0

        # Patterns for bracketed [N] and numbered N. styles
        _bracketed = re.compile(r"^\[(\d+)\]\s*(.+)")
        _numbered  = re.compile(r"^(\d+)\.\s+(.+)")
        # APA-style: starts with a word (author surname) followed by common reference tokens
        _apa       = re.compile(r"^[A-Z][a-zA-Zéàü\-]+(?:,\s*[A-Z]\.?)+.{10,}")

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            # Detect start of references section
            if re.match(r"^#{1,3}\s*(References|Bibliography|Works Cited)", stripped, re.IGNORECASE):
                ref_section = True
                continue

            if not ref_section:
                continue

            # Stop at the next top-level section (after References starts)
            if re.match(r"^#{1,2}\s+\w", stripped) and ref_counter:
                break

            m = _bracketed.match(stripped) or _numbered.match(stripped)
            if m:
                ref_counter += 1
                references.append(Reference(id=f"ref_{ref_counter:03d}", text=m.group(2)))
            elif _apa.match(stripped) and len(stripped) > 20:
                ref_counter += 1
                references.append(Reference(id=f"ref_{ref_counter:03d}", text=stripped))

        return references
