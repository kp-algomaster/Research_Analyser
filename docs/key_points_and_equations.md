# Key Points & Equations Reference

## For Spec-Driven Development & Code Generation

This document provides all key formulae, algorithms, and technical specifications
needed to implement or integrate with the Research Analyser pipeline.

---

## 1. MonkeyOCR 1.5 - Content Extraction

### 1.1 Architecture: Structure-Recognition-Relation (SRR) Triplet

```
Stage 1: Layout Structure + Reading Order Prediction
  Input: PDF page image
  Model: Multimodal LLM (3B parameters)
  Output: Bounding boxes + block types + reading order indices

Stage 2: Localized Content Recognition
  Input: Cropped regions from Stage 1
  Types: text | formula | table
  Output: Recognized content per block type
```

### 1.2 Equation Extraction Patterns

```python
# Display equations (block-level)
DISPLAY_PATTERNS = [
    r'\$\$(.+?)\$\$',                              # $$...$$
    r'\\\[(.+?)\\\]',                               # \[...\]
    r'\\begin\{equation\}(.+?)\\end\{equation\}',   # \begin{equation}...\end{equation}
    r'\\begin\{align\}(.+?)\\end\{align\}',         # \begin{align}...\end{align}
    r'\\begin\{gather\}(.+?)\\end\{gather\}',       # \begin{gather}...\end{gather}
]

# Inline equations
INLINE_PATTERNS = [
    r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)',         # $...$
    r'\\\((.+?)\\\)',                                # \(...\)
]

# Equation labels
LABEL_PATTERN = r'\\label\{(eq:[^}]+)\}'
```

### 1.3 Table Extraction (TEDS Format)

```
Tree-Edit Distance-based Similarity (TEDS):
  TEDS(T_pred, T_ref) = 1 - EditDist(T_pred, T_ref) / max(|T_pred|, |T_ref|)

Where:
  T_pred = predicted table tree structure
  T_ref  = reference table tree structure
  EditDist = tree edit distance (insertion, deletion, substitution costs)
```

### 1.4 Performance Benchmarks

```
MonkeyOCR-pro-3B on OmniDocBench v1.5:
  English Edit Score: 0.138 (lower is better)
  Chinese Edit Score: 0.206
  Table TEDS (EN): 81.5
  Table TEDS (CN): 87.5
  olmOCR-Bench: 75.8 ± 1.0

Processing Speed:
  RTX 4090: ~1.01 pages/second (3B model)
  RTX 4090: ~1.44 pages/second (1.2B model)
```

---

## 2. PaperBanana - Diagram Generation

### 2.1 Five-Agent Pipeline

```
Phase 0 (Optional - --optimize flag):
  Context Enricher: Expand abbreviated methodology text
  Caption Sharpener: Refine diagram captions for clarity

Phase 1 (Linear Planning):
  Agent 1 - Retriever:
    Input: Source text + caption
    Process: Semantic search over curated reference database
    Output: Top-10 most relevant reference diagram examples

  Agent 2 - Planner:
    Input: Source text + caption + reference examples
    Process: In-context learning to translate text → visual description
    Output: Detailed visual layout specification (JSON)

  Agent 3 - Stylist:
    Input: Visual specification + target venue
    Process: Apply aesthetic rules matching venue style (NeurIPS, ICML, CVPR, etc.)
    Output: Style-enhanced visual specification

Phase 2 (Iterative Refinement - default 3 rounds):
  Agent 4 - Visualizer:
    Input: Visual specification
    Process: Generate image via VLM image generation model
    Output: Rendered diagram image (PNG/SVG)

  Agent 5 - Critic:
    Input: Generated image + source text + caption
    Process: Evaluate faithfulness, completeness, aesthetics
    Output: Feedback text for next refinement round
    Metric: Critic score (0-1), target > 0.8
```

### 2.2 Generation Input Schema

```python
GenerationInput = {
    "source_context": str,       # Methodology text from paper
    "communicative_intent": str,  # What the diagram should convey
    "diagram_type": Enum[         # Type of diagram to generate
        "METHODOLOGY",            # Method/approach overview
        "ARCHITECTURE",           # Model/system architecture
        "RESULTS",                # Statistical plot
    ],
}
```

### 2.3 Settings Configuration

```python
PaperBananaSettings = {
    # VLM Provider (for planning and critique agents)
    "vlm_provider": "openai" | "google" | "openrouter",
    "vlm_model": str,  # e.g., "gpt-5.2", "gemini-2.0-flash"

    # Image Generation Provider (for visualizer agent)
    "image_provider": "openai_imagen" | "google_imagen",
    "image_model": str,  # e.g., "gpt-image-1.5", "gemini-3-pro-image-preview"

    # Pipeline options
    "optimize_inputs": bool,    # Enable Phase 0 preprocessing
    "auto_refine": bool,        # Enable Phase 2 iterative refinement
    "max_iterations": int,      # Refinement rounds (default: 3)
    "output_format": str,       # "png", "svg", "pdf", "webp"
    "resolution": str,          # "2k" (default), "4k"
}
```

### 2.4 Benchmark Performance

```
PaperBananaBench (292 NeurIPS 2025 methodology diagrams):
  Win rate vs baseline AI: 72.7% (blind human evaluation)
  Average refinement rounds to convergence: 2.3
```

---

## 3. Agentic Paper Review - Scoring System

### 3.1 Core Scoring Formula

```
Final Score = β₀ + β₁·S + β₂·P + β₃·C

Where:
  β₀ = -0.3057  (intercept)
  β₁ = 0.7134   (soundness weight)
  β₂ = 0.4242   (presentation weight)
  β₃ = 1.0588   (contribution weight)

  S = Soundness score     ∈ [1, 4]  (technical correctness)
  P = Presentation score  ∈ [1, 4]  (writing clarity)
  C = Contribution score  ∈ [1, 4]  (significance/novelty)

Final Score ∈ [1, 10]
```

### 3.2 Dimension Weight Distribution

```
                    Weight    Percentage
Soundness (S):      0.7134    32.5%
Presentation (P):   0.4242    19.3%
Contribution (C):   1.0588    48.2%

Confidence score ∈ [1, 5] (reported separately, not in final score)
```

### 3.3 Score Interpretation Scale

```
Score Range    Interpretation
[1.0, 3.0)     Strong Reject
[3.0, 4.0)     Reject
[4.0, 5.0)     Weak Reject
[5.0, 6.0)     Borderline
[6.0, 7.0)     Weak Accept
[7.0, 8.0)     Accept
[8.0, 10.0]    Strong Accept
```

### 3.4 Nine-Node LangGraph Workflow

```
Node 1: PaperIntake
  Input: PDF path + target venue
  Output: Validated paper metadata + markdown content
  Action: Extract title, verify it's an academic paper

Node 2: QueryGeneration
  Input: Paper markdown
  Output: Search queries at 3 specificity levels
  Levels: [benchmarks, related_problems, related_techniques]

Node 3: RelatedWorkSearch
  Input: Search queries
  Output: Candidate related papers from arXiv
  API: Tavily Search API (optional, enhances quality)

Node 4: PaperRanking
  Input: Candidate papers + original paper
  Output: Top-K ranked related papers by relevance
  Method: Title + abstract + author similarity scoring

Node 5: Summarization
  Input: Ranked related papers
  Output: Concise summaries of each related paper
  Method: Use existing abstracts or generate from full text

Node 6: StrengthIdentification
  Input: Paper markdown + related work summaries
  Output: List of paper strengths with evidence

Node 7: WeaknessAnalysis
  Input: Paper markdown + related work summaries
  Output: List of weaknesses with specific citations

Node 8: ReviewComposition
  Input: Strengths + weaknesses + related works
  Output: Structured review text (markdown)

Node 9: Scoring
  Input: Review text + dimensional analysis
  Output: Calibrated scores per dimension + final score
  Method: scikit-learn linear regression (trained on 46,748 ICLR reviews)
```

### 3.5 Correlation Metrics

```
Spearman correlation with human reviewers:
  Open-source (debashis1983): ρ = 0.74
  Stanford PaperReview.ai:    ρ = 0.42
  Human-to-human baseline:    ρ = 0.41
```

---

## 4. Integration Patterns

### 4.1 Full Pipeline Pseudocode

```python
async def analyse_paper(source: str) -> AnalysisReport:
    # 1. Resolve input
    pdf_path = await input_handler.resolve(source)

    # 2. Extract content with MonkeyOCR
    content = await ocr_engine.extract(pdf_path)

    # 3. Run analysis in parallel
    diagrams_task = diagram_generator.generate(
        content,
        diagram_types=["methodology", "architecture"]
    )
    review_task = reviewer.review(
        content,
        venue="ICLR 2026"
    )
    diagrams, review = await asyncio.gather(diagrams_task, review_task)

    # 4. Generate summary
    summary = summarizer.summarize(content, review)

    # 5. Assemble report
    report = AnalysisReport(
        extracted_content=content,
        review=review,
        diagrams=diagrams,
        summary=summary,
        key_points=extract_key_points(content, review),
    )

    # 6. Save outputs
    report_generator.save_all(report, output_dir="./output")

    return report
```

### 4.2 arXiv URL Resolution

```python
# arXiv ID patterns
ARXIV_PATTERNS = [
    r'arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)',     # https://arxiv.org/abs/2401.12345
    r'arxiv\.org/pdf/(\d{4}\.\d{4,5}(?:v\d+)?)',      # https://arxiv.org/pdf/2401.12345
    r'^(\d{4}\.\d{4,5}(?:v\d+)?)$',                    # Raw ID: 2401.12345
]

# Resolution
pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
api_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
```

### 4.3 DOI Resolution

```python
# DOI content negotiation for PDF
headers = {"Accept": "application/pdf"}
response = requests.get(f"https://doi.org/{doi}", headers=headers, allow_redirects=True)

# Fallback: get metadata first
headers = {"Accept": "application/json"}
metadata = requests.get(f"https://doi.org/{doi}", headers=headers).json()
pdf_url = metadata.get("link", [{}])[0].get("URL")
```

---

## 5. Output Format Specifications

### 5.1 Report Markdown Template

```markdown
---
title: "{paper_title}"
authors: [{authors}]
date_analysed: "{iso_date}"
source: "{source_url_or_path}"
tools: ["MonkeyOCR 1.5", "PaperBanana", "Agentic Reviewer"]
---

# Analysis Report: {paper_title}

## Summary
{ai_generated_summary}

## Key Findings
{numbered_key_findings}

## Key Equations
{equations_with_descriptions}

## Methodology
{methodology_summary}
![Methodology Diagram](./diagrams/methodology.png)

## Peer Review
**Overall Score: {score}/10** (Confidence: {confidence}/5)
### Strengths
{strengths_list}
### Weaknesses
{weaknesses_list}
### Suggestions
{suggestions_list}

## Dimensional Scores
| Dimension | Score | Weight |
|-----------|-------|--------|
| Soundness | {S}/4 | 32.5% |
| Presentation | {P}/4 | 19.3% |
| Contribution | {C}/4 | 48.2% |

## Related Work
{related_works_with_links}
```

### 5.2 Key Points Markdown Template (for Spec-Driven Dev)

```markdown
---
paper_id: "{id}"
extraction_model: "MonkeyOCR-pro-3B"
extraction_date: "{iso_date}"
---

# Key Points: {paper_title}

## Core Contributions
1. {contribution_1}
2. {contribution_2}

## Equations & Formulae

### Eq. 1: {equation_name}
$$
{latex_equation}
$$
> **Description:** {what_it_computes}
> **Variables:** {variable_definitions}
> **Used in:** {section_reference}

## Data Structures (Implied)
```python
# Structures implied by the paper's methodology
{implied_dataclass_definitions}
```

## Algorithm Steps
```
{algorithm_pseudocode}
```

## Reproducibility Checklist
- [ ] {reproducibility_item_1}
- [ ] {reproducibility_item_2}
```

### 5.3 Equations JSON Schema

```json
{
  "equations": [
    {
      "id": "eq_001",
      "latex": "L = \\sum_{i=1}^{N} -y_i \\log(\\hat{y}_i)",
      "type": "display",
      "label": "eq:loss",
      "section": "3.2 Training Objective",
      "context": "We minimize the cross-entropy loss...",
      "description": "Cross-entropy loss function for classification",
      "variables": {
        "L": "Total loss",
        "N": "Number of samples",
        "y_i": "Ground truth label for sample i",
        "\\hat{y}_i": "Predicted probability for sample i"
      }
    }
  ]
}
```

---

## 6. Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...              # For agentic reviewer LLM

# Diagram Generation (one of these)
GOOGLE_API_KEY=...                  # Google Gemini (free tier available)
OPENAI_API_KEY=sk-...               # OpenAI (shared with reviewer)

# Optional
TAVILY_API_KEY=tvly-...            # Enhanced related work search
SEMANTIC_SCHOLAR_API_KEY=...        # Higher rate limits for paper metadata
HF_TOKEN=hf_...                    # HuggingFace (for MonkeyOCR model download)

# Configuration
RESEARCH_ANALYSER_CONFIG=./config.yaml
RESEARCH_ANALYSER_OUTPUT_DIR=./output
RESEARCH_ANALYSER_LOG_LEVEL=INFO
```
