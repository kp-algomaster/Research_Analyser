# Research Analyser - Specification Document

## Spec-Driven Development Guide

This document defines the complete specification for the Research Analyser application.
It is designed for use with AI-assisted code generation tools (Claude Code, Cursor, Copilot)
to produce implementation code from these specifications.

---

## 1. System Overview

### 1.1 Purpose
Automated research paper analysis combining OCR extraction, AI diagram generation,
and agentic peer review into a unified pipeline.

### 1.2 Core Pipeline

```
Input (PDF/URL) → Extraction (MonkeyOCR) → Analysis (Review + Diagrams) → Output (Reports)
```

### 1.3 Component Dependencies

| Component | Library | Version | Source |
|-----------|---------|---------|--------|
| OCR Engine | MonkeyOCR | 1.5 (pro-3B) | github.com/Yuliang-Liu/MonkeyOCR |
| Diagram Generator | PaperBanana | latest | github.com/llmsresearch/paperbanana |
| Paper Reviewer | agentic-paper-review | latest | github.com/debashis1983/agentic-paper-review |
| Web Framework | Streamlit | >=1.30 | pypi.org/project/streamlit |
| API Framework | FastAPI | >=0.100 | pypi.org/project/fastapi |
| PDF Processing | PyMuPDF | >=1.23 | pypi.org/project/PyMuPDF |

---

## 2. Data Models

### 2.1 PaperInput

```python
@dataclass
class PaperInput:
    """Input specification for paper analysis."""
    source_type: Literal["pdf_file", "pdf_url", "arxiv_id", "doi"]
    source_value: str  # file path, URL, arXiv ID, or DOI
    target_venue: Optional[str] = None  # e.g., "ICLR 2026", "NeurIPS 2026"
    analysis_options: AnalysisOptions = field(default_factory=AnalysisOptions)
```

### 2.2 AnalysisOptions

```python
@dataclass
class AnalysisOptions:
    """Configuration for what analysis to perform."""
    extract_text: bool = True
    extract_equations: bool = True
    extract_tables: bool = True
    extract_figures: bool = True
    generate_diagrams: bool = True
    generate_review: bool = True
    generate_audio: bool = False
    generate_summary: bool = True
    generate_storm_report: bool = False    # STORM Wikipedia-style report (requires knowledge-storm)
    diagram_types: list[str] = field(default_factory=lambda: ["methodology", "architecture"])
    diagram_provider: Literal["openai", "google", "openrouter"] = "google"
    review_dimensions: list[str] = field(default_factory=lambda: [
        "soundness", "presentation", "contribution"
    ])
    output_format: Literal["markdown", "json", "html"] = "markdown"
```

### 2.3 ExtractedContent

```python
@dataclass
class ExtractedContent:
    """Content extracted from paper via MonkeyOCR."""
    full_text: str                          # Complete markdown text
    title: str                              # Paper title
    authors: list[str]                      # Author list
    abstract: str                           # Abstract text
    sections: list[Section]                 # Parsed sections
    equations: list[Equation]               # LaTeX equations
    tables: list[Table]                     # Extracted tables
    figures: list[Figure]                   # Detected figures
    references: list[Reference]             # Bibliography
    reading_order: list[int]                # Block reading order
    metadata: dict                          # Additional metadata
```

### 2.4 Equation

```python
@dataclass
class Equation:
    """Mathematical equation extracted from paper."""
    id: str                                 # Unique identifier
    latex: str                              # LaTeX representation
    context: str                            # Surrounding text context
    section: str                            # Section where found
    is_inline: bool                         # Inline vs display equation
    label: Optional[str] = None             # Equation label/number
    description: Optional[str] = None       # AI-generated description
```

### 2.5 AnalysisReport

```python
@dataclass
class AnalysisReport:
    """Complete analysis output."""
    paper_input: PaperInput
    extracted_content: ExtractedContent
    review: Optional[PeerReview]
    diagrams: list[GeneratedDiagram]
    summary: PaperSummary
    key_points: list[KeyPoint]
    metadata: ReportMetadata
    storm_report: Optional[str] = None    # STORM Wikipedia-style article (None if not generated)

    def to_markdown(self) -> str: ...
    def to_json(self) -> dict: ...
    def save(self, output_dir: str) -> None: ...
```

### 2.6 PeerReview

```python
@dataclass
class PeerReview:
    """Structured peer review output."""
    overall_score: float                    # 1-10 scale
    confidence: float                       # 1-5 scale
    dimensions: dict[str, DimensionScore]   # Scored dimensions
    strengths: list[str]                    # Identified strengths
    weaknesses: list[str]                   # Identified weaknesses
    suggestions: list[str]                  # Improvement suggestions
    related_works: list[RelatedWork]        # Found related papers
    raw_review: str                         # Full review text

    # Score formula: -0.3057 + 0.7134*Soundness + 0.4242*Presentation + 1.0588*Contribution
```

### 2.7 GeneratedDiagram

```python
@dataclass
class GeneratedDiagram:
    """Diagram generated by PaperBanana."""
    diagram_type: str                       # "methodology", "architecture", "plot"
    image_path: str                         # Path to generated image
    caption: str                            # Diagram caption
    source_context: str                     # Text used to generate
    iterations: int                         # Refinement iterations used
    format: str                             # "png", "svg", "pdf"
```

---

## 3. Module Specifications

### 3.1 Input Handler Module (`research_analyser/input_handler.py`)

**Purpose:** Resolve and fetch papers from various input sources.

**Interface:**
```python
class InputHandler:
    async def resolve(self, paper_input: PaperInput) -> Path:
        """Resolve input to a local PDF file path.

        - pdf_file: Validate file exists, return path
        - pdf_url: Download PDF, return local path
        - arxiv_id: Resolve to PDF URL via arXiv API, download
        - doi: Resolve via DOI.org, follow to publisher PDF

        Returns: Path to local PDF file
        Raises: InputError on invalid/unreachable source
        """

    async def fetch_arxiv(self, arxiv_id: str) -> Path:
        """Fetch PDF from arXiv. ID format: 2401.12345 or 2401.12345v2"""

    async def fetch_url(self, url: str) -> Path:
        """Download PDF from direct URL with retry logic."""

    async def resolve_doi(self, doi: str) -> str:
        """Resolve DOI to PDF URL via content negotiation."""
```

**Key Equations/Formulae:**
- arXiv PDF URL pattern: `https://arxiv.org/pdf/{arxiv_id}.pdf`
- DOI resolution: `https://doi.org/{doi}` with `Accept: application/pdf` header
- Semantic Scholar API: `https://api.semanticscholar.org/graph/v1/paper/{paper_id}`

### 3.2 OCR Engine Module (`research_analyser/ocr_engine.py`)

**Purpose:** Extract structured content from PDF using MonkeyOCR 1.5.

**Interface:**
```python
class OCREngine:
    def __init__(self, model_name: str = "MonkeyOCR-pro-3B", device: str = "auto"):
        """Initialize MonkeyOCR model.

        Args:
            model_name: Model variant (MonkeyOCR-pro-3B, MonkeyOCR-pro-1.2B)
            device: "cuda", "cpu", or "auto"
        """

    async def extract(self, pdf_path: Path) -> ExtractedContent:
        """Full extraction pipeline.

        Pipeline:
        1. Load PDF, split into pages
        2. Run MonkeyOCR parse on each page
        3. Merge page results into unified document
        4. Post-process: equation detection, table parsing, figure extraction
        5. Build structured ExtractedContent object

        Returns: ExtractedContent with all parsed elements
        """

    def extract_equations(self, markdown_text: str) -> list[Equation]:
        """Parse LaTeX equations from MonkeyOCR markdown output.

        Detection patterns:
        - Display: $$...$$ or \\[...\\] or \\begin{equation}...\\end{equation}
        - Inline: $...$ or \\(...\\)
        - Labeled: \\label{eq:name} within equation environments
        """

    def extract_tables(self, blocks: list[dict]) -> list[Table]:
        """Extract tables from MonkeyOCR block output."""

    def parse_sections(self, markdown_text: str) -> list[Section]:
        """Parse document into hierarchical sections from markdown headers."""
```

**Key Processing:**
- MonkeyOCR outputs: `document.md` (markdown), `document_layout.pdf` (visual), `document_middle.json` (blocks)
- Equation regex: `r'\$\$(.+?)\$\$'` (display), `r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)'` (inline)
- Table detection: MonkeyOCR block type `"table"` with TEDS format

### 3.3 Diagram Generator Module (`research_analyser/diagram_generator.py`)

**Purpose:** Generate publication-quality diagrams using PaperBanana.

**Interface:**
```python
class DiagramGenerator:
    def __init__(self, settings: Optional[PaperBananaSettings] = None):
        """Initialize PaperBanana pipeline.

        Default settings use Google Gemini free tier.
        """

    async def generate(
        self,
        content: ExtractedContent,
        diagram_types: list[str] = ["methodology"],
        auto_refine: bool = True,
    ) -> list[GeneratedDiagram]:
        """Generate diagrams from extracted paper content.

        Pipeline:
        1. Identify relevant sections for each diagram type
        2. Build GenerationInput with source context + caption
        3. Run PaperBanana pipeline (Retriever→Planner→Stylist→Visualizer→Critic)
        4. Collect and return generated diagrams

        Diagram types:
        - "methodology": Method/approach overview from methodology sections
        - "architecture": Model/system architecture from architecture sections
        - "results": Statistical plots from results/experiments sections
        """

    async def generate_methodology(self, content: ExtractedContent) -> GeneratedDiagram:
        """Generate methodology overview diagram."""

    async def generate_architecture(self, content: ExtractedContent) -> GeneratedDiagram:
        """Generate architecture diagram."""

    async def generate_results_plot(
        self, content: ExtractedContent, data: Optional[dict] = None
    ) -> GeneratedDiagram:
        """Generate results visualization plot."""
```

**PaperBanana Pipeline Stages:**
1. **Retriever** - Selects 10 most relevant reference examples
2. **Planner** - Translates text into visual description via in-context learning
3. **Stylist** - Refines for aesthetics matching target venue style
4. **Visualizer** - Renders descriptions into images (3 refinement rounds)
5. **Critic** - Evaluates output against source text

### 3.4 Reviewer Module (`research_analyser/reviewer.py`)

**Purpose:** Generate structured peer review using agentic review pipeline.

**Interface:**
```python
class PaperReviewer:
    def __init__(
        self,
        llm_provider: str = "openai",
        model: str = "gpt-4o",
        tavily_api_key: Optional[str] = None,
    ):
        """Initialize agentic reviewer.

        Uses LangGraph workflow with Plan-Execute-Reflect pattern.
        """

    async def review(
        self,
        content: ExtractedContent,
        venue: Optional[str] = None,
    ) -> PeerReview:
        """Generate comprehensive peer review.

        9-node LangGraph workflow:
        1. Paper intake & validation
        2. Search query generation (varying specificity levels)
        3. Related work search (arXiv via Tavily)
        4. Paper ranking by relevance
        5. Related work summarization
        6. Strength identification
        7. Weakness analysis
        8. Review composition
        9. Multi-dimensional scoring with ML calibration

        Scoring dimensions:
        - Soundness (32.5% weight): Technical correctness
        - Presentation (19.3% weight): Clarity of writing
        - Contribution (48.2% weight): Significance/novelty

        Final score formula:
        score = -0.3057 + 0.7134 * soundness + 0.4242 * presentation + 1.0588 * contribution
        """
```

**Key Formulae:**

| Formula | Description |
|---------|-------------|
| `score = -0.3057 + 0.7134*S + 0.4242*P + 1.0588*C` | Final review score (1-10) |
| `S` = Soundness score (1-4) | Technical correctness weight: 32.5% |
| `P` = Presentation score (1-4) | Writing clarity weight: 19.3% |
| `C` = Contribution score (1-4) | Significance/novelty weight: 48.2% |
| `confidence ∈ [1,5]` | Reviewer confidence (not in final score) |

### 3.5 Report Generator Module (`research_analyser/report_generator.py`)

**Purpose:** Assemble all analysis components into structured output reports.

**Interface:**
```python
class ReportGenerator:
    def generate_report(self, report: AnalysisReport) -> str:
        """Generate full markdown analysis report."""

    def generate_key_points(self, report: AnalysisReport) -> str:
        """Generate key points and equations summary markdown."""

    def generate_spec_output(self, report: AnalysisReport) -> str:
        """Generate spec-driven output for downstream code generation.

        Machine-readable markdown with:
        - Paper metadata block (YAML frontmatter)
        - Structured key findings
        - Equations in LaTeX with descriptions
        - API signatures implied by methodology
        - Data structures implied by results
        """

    def save_all(self, report: AnalysisReport, output_dir: Path) -> None:
        """Save all outputs to directory structure.

        Output files:
        - report.md            Full markdown analysis report
        - key_points.md        Key findings and equations summary
        - spec_output.md       Machine-readable spec-driven output
        - report.html          HTML report with MathJax equations
        - review.md            Raw peer review (if generated)
        - storm_report.md      STORM Wikipedia-style article (if generated)
        - extracted/           full_text.md, equations.json, tables.json
        - metadata.json        Pipeline run metadata
        """
```

### 3.7 STORM Reporter (`research_analyser/storm_reporter.py`)

**Purpose:** Generate Wikipedia-style cited articles from paper content using Stanford OVAL's
`knowledge-storm` library. Requires `pip install knowledge-storm`.

**Interface:**
```python
class STORMReporter:
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        conv_model: str = "gpt-4o-mini",
        outline_model: str = "gpt-4o",
        article_model: str = "gpt-4o",
        max_conv_turn: int = 3,
        max_perspective: int = 3,
        search_top_k: int = 5,
        retrieve_top_k: int = 5,
    ): ...

    def generate(self, report: AnalysisReport) -> str:
        """Run STORM pipeline. Returns polished article text.
        Blocking — call via asyncio.to_thread in async contexts.
        Raises: ImportError if knowledge-storm not installed.
        """

class PaperContentRM(dspy.Retrieve):
    """Custom retrieval module backed by the paper's extracted content.
    No external API or vector database required.
    """
    def __init__(self, content: ExtractedContent, k: int = 5): ...
    def forward(self, query_or_queries, exclude_urls=None) -> list[dspy.Example]: ...
```

### 3.6 Main Orchestrator (`research_analyser/analyser.py`)

**Purpose:** Coordinate all modules in the analysis pipeline.

**Interface:**
```python
class ResearchAnalyser:
    def __init__(self, config: Optional[Config] = None):
        """Initialize all pipeline components."""

    async def analyse(
        self,
        source: str,
        source_type: Optional[str] = None,
        options: Optional[AnalysisOptions] = None,
    ) -> AnalysisReport:
        """Run complete analysis pipeline.

        Flow:
        1. Detect source type (PDF file, URL, arXiv ID, DOI)
        2. Resolve to local PDF via InputHandler
        3. Extract content via OCREngine (MonkeyOCR)
        4. Run in parallel:
           a. Generate diagrams via DiagramGenerator (PaperBanana)
           b. Generate review via PaperReviewer (Agentic Review)
        5. Assemble AnalysisReport
        6. Generate output files via ReportGenerator

        Returns: Complete AnalysisReport
        """
```

---

## 4. API Specification

### 4.1 REST API Endpoints

```
POST   /api/v1/analyse              # Submit paper for analysis
GET    /api/v1/analyse/{job_id}      # Get analysis status/results
POST   /api/v1/extract              # Extract content only (no review/diagrams)
POST   /api/v1/review               # Generate review only
POST   /api/v1/diagrams             # Generate diagrams only
GET    /api/v1/health               # Health check
```

### 4.2 Request/Response Models

```python
# POST /api/v1/analyse
class AnalyseRequest(BaseModel):
    source: str                          # URL, arXiv ID, or "upload"
    source_type: Optional[str] = None    # Auto-detected if None
    venue: Optional[str] = None
    generate_diagrams: bool = True
    generate_review: bool = True
    diagram_types: list[str] = ["methodology"]

class AnalyseResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    report: Optional[AnalysisReport] = None
    error: Optional[str] = None
```

### 4.3 File Upload

```python
# POST /api/v1/analyse (multipart/form-data)
@app.post("/api/v1/analyse")
async def analyse_paper(
    file: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None),
    venue: Optional[str] = Form(None),
    generate_diagrams: bool = Form(True),
    generate_review: bool = Form(True),
):
    ...
```

---

## 5. Configuration Schema

```yaml
# config.yaml
app:
  name: "Research Analyser"
  output_dir: "./output"
  temp_dir: "./tmp"
  log_level: "INFO"

ocr:
  model: "MonkeyOCR-pro-3B"        # or "MonkeyOCR-pro-1.2B" for faster processing
  device: "auto"                     # "cuda", "cpu", or "auto"
  page_split: true
  output_format: "markdown"

diagrams:
  provider: "google"                 # "openai", "google", "openrouter"
  vlm_model: "gemini-2.0-flash"     # Vision-language model for planning
  image_model: "gemini-3-pro-image-preview"  # Image generation model
  optimize_inputs: true
  auto_refine: true
  max_iterations: 3
  output_format: "png"               # "png", "svg", "pdf"
  resolution: "2k"

review:
  llm_provider: "openai"
  model: "gpt-4o"
  use_tavily: true                   # Enhanced related work search
  scoring_weights:
    soundness: 0.7134
    presentation: 0.4242
    contribution: 1.0588
  intercept: -0.3057

storm:
  enabled: false                     # Set true to generate STORM Wikipedia-style report
  conv_model: "gpt-4o-mini"          # Model for conversation simulation
  outline_model: "gpt-4o"            # Model for outline generation
  article_model: "gpt-4o"            # Model for article writing and polishing
  max_conv_turn: 3                   # Max conversation turns per perspective (min 1)
  max_perspective: 3                 # Number of expert perspectives (min 1)
  search_top_k: 5                    # Chunks fetched per search query (min 1)
  retrieve_top_k: 5                  # Chunks used per retrieval step (min 1)

api:
  host: "0.0.0.0"
  port: 8000
  max_upload_size_mb: 100
  job_timeout_seconds: 600
```

---

## 6. Error Handling

```python
class ResearchAnalyserError(Exception): ...
class InputError(ResearchAnalyserError): ...       # Invalid input source
class ExtractionError(ResearchAnalyserError): ...  # MonkeyOCR failure
class DiagramError(ResearchAnalyserError): ...     # PaperBanana failure
class ReviewError(ResearchAnalyserError): ...      # Reviewer failure
class ConfigError(ResearchAnalyserError): ...      # Configuration error
```

---

## 7. Testing Strategy

```
tests/
├── unit/
│   ├── test_input_handler.py       # URL resolution, arXiv fetching
│   ├── test_ocr_engine.py          # Equation parsing, section detection
│   ├── test_diagram_generator.py   # Diagram type selection
│   ├── test_reviewer.py            # Score calculation
│   └── test_report_generator.py    # Markdown generation
├── integration/
│   ├── test_full_pipeline.py       # End-to-end with sample paper
│   └── test_api.py                 # FastAPI endpoint testing
└── fixtures/
    ├── sample_paper.pdf            # Test PDF
    ├── sample_markdown.md          # Pre-extracted content
    └── sample_equations.json       # Known equations for validation
```
