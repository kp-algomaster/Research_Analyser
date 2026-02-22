"""Input handling: resolve PDFs from URLs, arXiv IDs, DOIs, and local files."""

from __future__ import annotations

import logging
import json
import re
import tempfile
import tarfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Optional

import aiohttp

from research_analyser.exceptions import InputError
from research_analyser.models import PaperInput, SourceType

logger = logging.getLogger(__name__)

# arXiv ID patterns
ARXIV_PATTERNS = [
    re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)"),
    re.compile(r"arxiv\.org/pdf/(\d{4}\.\d{4,5}(?:v\d+)?)"),
    re.compile(r"^(\d{4}\.\d{4,5}(?:v\d+)?)$"),
]

DOI_PATTERN = re.compile(r"^10\.\d{4,}/[^\s]+$")


class InputHandler:
    """Resolve and fetch papers from various input sources."""

    def __init__(self, temp_dir: Optional[str] = None):
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp())
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def detect_source_type(self, source: str) -> SourceType:
        """Auto-detect the type of input source."""
        path = Path(source)
        if path.exists() and path.suffix.lower() == ".pdf":
            return SourceType.PDF_FILE

        for pattern in ARXIV_PATTERNS:
            if pattern.search(source):
                return SourceType.ARXIV_ID

        if DOI_PATTERN.match(source):
            return SourceType.DOI

        if source.startswith(("http://", "https://")):
            return SourceType.PDF_URL

        raise InputError(f"Cannot determine source type for: {source}")

    async def resolve(self, paper_input: PaperInput) -> Path:
        """Resolve input to a local PDF file path."""
        match paper_input.source_type:
            case SourceType.PDF_FILE:
                return self._resolve_local(paper_input.source_value)
            case SourceType.PDF_URL:
                return await self.fetch_url(paper_input.source_value)
            case SourceType.ARXIV_ID:
                arxiv_id = self._extract_arxiv_id(paper_input.source_value)
                return await self.fetch_arxiv(arxiv_id)
            case SourceType.DOI:
                return await self._resolve_doi(paper_input.source_value)
            case _:
                raise InputError(f"Unknown source type: {paper_input.source_type}")

    def _resolve_local(self, file_path: str) -> Path:
        """Validate and return local file path."""
        path = Path(file_path)
        if not path.exists():
            raise InputError(f"File not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise InputError(f"Not a PDF file: {file_path}")
        return path

    def _extract_arxiv_id(self, source: str) -> str:
        """Extract arXiv ID from various input formats."""
        for pattern in ARXIV_PATTERNS:
            match = pattern.search(source)
            if match:
                return match.group(1)
        raise InputError(f"Cannot extract arXiv ID from: {source}")

    async def fetch_arxiv(self, arxiv_id: str) -> Path:
        """Fetch PDF from arXiv."""
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        logger.info(f"Fetching arXiv paper: {arxiv_id}")
        pdf_path = await self.fetch_url(pdf_url, filename=f"arxiv_{arxiv_id}.pdf")

        metadata = await self._fetch_arxiv_metadata(arxiv_id)
        if metadata:
            metadata_path = pdf_path.with_suffix(".meta.json")
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        tex_source = await self._fetch_arxiv_tex_source(arxiv_id)
        if tex_source:
            tex_path = pdf_path.with_suffix(".source.tex")
            tex_path.write_text(tex_source, encoding="utf-8")

        return pdf_path

    async def _fetch_arxiv_tex_source(self, arxiv_id: str) -> Optional[str]:
        """Fetch TeX source bundle from arXiv e-print endpoint."""
        source_url = f"https://arxiv.org/e-print/{arxiv_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(source_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        return None
                    content = await resp.read()

            extracted_tex = []
            with tarfile.open(fileobj=BytesIO(content), mode="r:*") as tar:
                for member in tar.getmembers():
                    if not member.isfile() or not member.name.endswith(".tex"):
                        continue
                    extracted_file = tar.extractfile(member)
                    if extracted_file is None:
                        continue
                    data = extracted_file.read()
                    text = data.decode("utf-8", errors="ignore")
                    if text.strip():
                        extracted_tex.append(text)

            if extracted_tex:
                logger.info(f"Fetched arXiv source with {len(extracted_tex)} TeX file(s)")
                return "\n\n".join(extracted_tex)

            return None
        except Exception as e:
            logger.warning(f"Failed to fetch arXiv source for {arxiv_id}: {e}")
            return None

    async def _fetch_arxiv_metadata(self, arxiv_id: str) -> Optional[dict]:
        """Fetch title/authors/abstract from arXiv API."""
        api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        return None
                    xml_text = await resp.text()

            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is None:
                return None

            title = entry.findtext("atom:title", default="", namespaces=ns).strip()
            summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
            authors = [
                author.findtext("atom:name", default="", namespaces=ns).strip()
                for author in entry.findall("atom:author", ns)
            ]
            authors = [author for author in authors if author]

            return {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "abstract": summary,
            }
        except Exception as e:
            logger.warning(f"Failed to fetch arXiv metadata for {arxiv_id}: {e}")
            return None

    async def fetch_url(
        self, url: str, filename: Optional[str] = None, max_retries: int = 3
    ) -> Path:
        """Download PDF from URL with retry logic."""
        if filename is None:
            filename = url.split("/")[-1]
            if not filename.endswith(".pdf"):
                filename += ".pdf"

        output_path = self.temp_dir / filename

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status != 200:
                            raise InputError(
                                f"HTTP {resp.status} fetching {url}"
                            )

                        content = await resp.read()
                        output_path.write_bytes(content)
                        logger.info(f"Downloaded {len(content)} bytes to {output_path}")
                        return output_path

            except aiohttp.ClientError as e:
                if attempt == max_retries - 1:
                    raise InputError(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {url}: {e}")

        raise InputError(f"Failed to fetch {url}")

    async def _resolve_doi(self, doi: str) -> Path:
        """Resolve DOI to PDF URL and download."""
        url = f"https://doi.org/{doi}"
        logger.info(f"Resolving DOI: {doi}")

        async with aiohttp.ClientSession() as session:
            # Try direct PDF content negotiation
            headers = {"Accept": "application/pdf"}
            async with session.get(
                url, headers=headers, allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200 and "pdf" in resp.content_type:
                    output_path = self.temp_dir / f"doi_{doi.replace('/', '_')}.pdf"
                    content = await resp.read()
                    output_path.write_bytes(content)
                    return output_path

            # Fallback: get metadata to find PDF link
            headers = {"Accept": "application/json"}
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status == 200:
                    metadata = await resp.json()
                    links = metadata.get("link", [])
                    for link in links:
                        if link.get("content-type") == "application/pdf":
                            return await self.fetch_url(link["URL"])

        raise InputError(f"Could not resolve DOI to PDF: {doi}")
