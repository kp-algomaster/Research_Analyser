# Contract: Research Analyser API Client

`src/api/ResearchAnalyserClient.ts` wraps all HTTP communication with the Research Analyser backend.

Base URL: `vscode.workspace.getConfiguration("researchAnalyser").get("apiUrl")` (default `http://localhost:8000`)

---

## Endpoints Used

### `GET /health`
**Purpose**: Check if server is running
**Response**: `200 OK` with `{ "status": "ok" }`
**Used by**: Activation check; "Start server?" prompt; `researchAnalyser.serverRunning` context key

### `GET /report/latest`
**Purpose**: Auto-load the most recent analysis report on extension activation
**Response**: `200 OK` with `AnalysisReport` JSON
**Response (none)**: `404 Not Found`

### `POST /analyse`
**Purpose**: Trigger a full analysis pipeline run
**Request body**:
```json
{
  "source": "2405.12345",
  "options": {
    "generate_diagrams": true,
    "generate_review": true,
    "generate_storm_report": false,
    "generate_audio": false,
    "diagram_types": ["methodology", "architecture"]
  }
}
```
**Response**: `200 OK` with `AnalysisReport` JSON (blocking; use `/analyse/stream` for progress)

### `POST /analyse/stream` *(SSE — needs adding to `research_analyser/api.py`)*
**Purpose**: Trigger analysis with Server-Sent Events progress stream
**Request body**: Same as `POST /analyse`
**Response**: `text/event-stream`

SSE event format:
```
event: progress
data: {"pct": 40, "message": "✓ OCR complete — 12 sections"}

event: progress
data: {"pct": 75, "message": "✓ 2 diagrams ready"}

event: complete
data: { ...AnalysisReport... }

event: error
data: {"message": "OCR failed: model not loaded"}
```

### `GET /equations`
**Purpose**: Fetch equations from the latest report without loading the full report
**Response**: `200 OK` with `Equation[]`

---

## Client Interface

```typescript
export interface IResearchAnalyserClient {
  /** Check if the server is reachable */
  health(): Promise<boolean>;

  /** Fetch the most recent report (null if none exists) */
  getLatestReport(): Promise<AnalysisReport | null>;

  /** Run analysis; resolve when complete (no progress) */
  analyse(req: AnalyseRequest): Promise<AnalysisReport>;

  /**
   * Run analysis with SSE progress stream.
   * @param onProgress called for each progress event
   * @param signal AbortSignal to cancel the stream
   */
  analyseStream(
    req: AnalyseRequest,
    onProgress: (event: ProgressEvent) => void,
    signal?: AbortSignal
  ): Promise<AnalysisReport>;
}
```

---

## Error Handling

| HTTP status | Client behaviour |
|-------------|-----------------|
| `200` | Parse JSON; validate structure |
| `404` | Return `null` (no report yet) |
| `422` | `showErrorMessage("Invalid input: ...")`|
| `500` | `showErrorMessage("Server error: ...")`|
| Network error | `showErrorMessage("Cannot reach Research Analyser at {url}")` + prompt to start server |
| SSE `event: error` | Reject promise with error message; show notification |

---

## Retry / Timeout Policy

- `health()`: single call, 2 s timeout
- `getLatestReport()`: single call, 5 s timeout; no retry
- `analyse()`: 300 s timeout (analysis can take minutes); no auto-retry
- `analyseStream()`: no timeout (SSE stream runs until `event: complete` or `event: error`); supports AbortSignal for user cancellation

---

## Backend Change Required

Add to `research_analyser/api.py`:
```python
from sse_starlette.sse import EventSourceResponse

@app.post("/analyse/stream")
async def analyse_stream(request: AnalyseRequest):
    async def generate():
        async for pct, msg in analyser.analyse_stream(request.source, request.options):
            yield {"event": "progress", "data": json.dumps({"pct": pct, "message": msg})}
        report = analyser.last_report
        yield {"event": "complete", "data": report.json()}
    return EventSourceResponse(generate())
```
This is tracked as a separate task in `tasks.md`.
