# LLM Test Generator

Automated unit test generation and evaluation framework powered by Google Gemini.  
Upload any Python file, and the system generates pytest tests, runs them, and reports pass rate, code coverage, mutation score, and assertion quality — all compared against a human-written baseline.

---

## Requirements

- **Python 3.10+**
- **Google Gemini API key** — get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey)

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/malekgr/CIS613PROJECT.git
cd CIS613PROJECT/
```

### 2. Install dependencies

```bash
pip install -r requirements.txt        # core (pytest, coverage, Gemini SDK)
pip install -r requirements_app.txt    # web UI (FastAPI, uvicorn)
```

### 3. Set your Gemini API key

```bash
export GEMINI_API_KEY="your-api-key-here"
```

To avoid setting it every session, add it permanently to your shell profile:

```bash
# macOS / Linux (bash)
echo 'export GEMINI_API_KEY="your-api-key-here"' >> ~/.bashrc && source ~/.bashrc
```

---

## Running the Project

### Web Interface

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

**Workflow:**

1. Drag and drop any `.py` file onto the upload zone
2. The **Chunk Explorer** button appears — click it to preview exactly what context will be assembled for each function before spending any API tokens
3. Click **Generate & Test** and watch sub-step progress in the live log:
   - `→ building context chunk…`
   - `→ calling LLM (gemini-2.5-flash-lite)…`
   - `→ running pytest + coverage…`
   - `→ computing coverage & mutation score…`
4. Review results in the tabs: per-function metrics, failure inspector, chunk viewer, Markdown report
5. Download CSV / JSON / Markdown from the **Downloads** tab



---

## Project Structure

```
.
├── app/
│   ├── main.py                  # FastAPI backend — jobs, polling, chunk preview
│   └── templates/index.html     # Single-page web UI
│
├── dataset/
│   ├── sample_functions.py      # 8 benchmark functions
│   └── human_tests/             # Hand-written baseline tests for all 8 functions
│
├── src/
│   ├── chunker.py               # SmartChunker — 6 context assembly strategies
│   ├── dependency_graph.py      # AST call-graph (no import needed)
│   ├── class_parser.py          # Class / method structure extraction
│   ├── token_budget.py          # Token estimation and cost tracking
│   ├── llm_generator.py         # Gemini API wrapper with retry + model fallback
│   ├── prompt_builder.py        # Prompt construction with anti-hallucination rules
│   ├── pipeline.py              # End-to-end orchestration per function
│   ├── metrics.py               # Coverage parsing + custom mutation engine
│   ├── test_runner.py           # pytest + pytest-cov subprocess wrapper
│   ├── failure_analyzer.py      # Classifies failures into 9 research categories
│   ├── report_generator.py      # CSV / JSON / Markdown output
│   ├── benchmark_runner.py      # Multi-function experiment runner
│   ├── loader.py                # Source file / function loader
│   ├── parser.py                # AST context extractor (legacy path)
│   └── comparator.py            # Side-by-side metric comparison printer
│
├── main.py                      # CLI entry point — single function
├── run_benchmark.py             # CLI entry point — full benchmark
├── rebuild_results.py           # Re-run metrics on existing tests (no LLM)
├── requirements.txt             # Core dependencies
└── requirements_app.txt         # Web UI dependencies
```

---

## Chunking Strategies

The system never sends the whole file to the LLM. Instead, `SmartChunker` assembles the minimum relevant context using one of six strategies:

| Mode | What is sent to the LLM |
|------|------------------------|
| `function_only` | Target function + module imports |
| `function_plus_deps` | Target + all transitively-called helper functions |
| `class_context` | Class shell (stubs for siblings, full source for called methods) + top-level deps |
| `hierarchical_summary` | Full context for relevant code + one-line stubs for everything else |
| `token_budget` | Greedy fill up to 6 000 tokens in priority order |
| `full_source` | Entire file (ablation baseline) |

The web UI automatically uses:
- `class_context` for class methods (e.g. `OrderService.place_order`)
- `function_plus_deps` for plain functions (e.g. `factorial`)

---

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| **Pass rate** | Fraction of generated tests that pass |
| **Function coverage** | Line coverage scoped to the target function |
| **Branch coverage** | Fraction of if/else paths exercised |
| **Mutation score** | Fraction of injected code faults detected by the tests |
| **Value assertion ratio** | Fraction of assertions checking concrete values (not bare truthiness) |



### Failure categories

| Category | Meaning |
|----------|---------|
| `oracle_error` | Wrong hardcoded expected value |
| `hallucinated_behavior` | LLM asserted behavior absent from the source |
| `type_assumption_error` | LLM assumed a type constraint not in the code |
| `import_error` | Wrong import path in the generated test |
| `expected_exception_missing` | `pytest.raises` but no exception was raised |
| `wrong_exception_type` | Exception raised but of the wrong class |
| `unsupported_edge_case` | Edge case (unicode, encoding) not covered by the spec |
| `flaky_generation` | Non-deterministic or unclassifiable failure |

---

## Output Files

| File | Contents |
|------|----------|
| `results_table.csv` | Per-function raw metrics |
| `mode_summary.csv` | Aggregated averages per mode |
| `category_summary.csv` | Failure category breakdown |
| `failure_summary.json` | Structured failure details |
| `report.md` | Full narrative Markdown report |
| `all_results.json` | Complete raw results |

---

## LLM Model & Automatic Fallback

Default model: **`gemini-2.5-flash-lite`**

When a model returns 503 / high-demand errors, the system automatically falls back through:

```
gemini-2.5-flash-lite → gemini-2.0-flash → gemini-1.5-flash
```

You will see `[fallback] succeeded with gemini-2.0-flash` in the progress log when a fallback is triggered.

---

## Design Choices

### SmartChunker vs. full-file prompting

Sending the entire file to the LLM wastes tokens on irrelevant code and increases cost linearly with file size. SmartChunker uses static AST call-graph analysis to assemble only the context the LLM needs: the target function, its transitive dependencies, and (for class methods) a condensed class shell with full source for directly-called siblings. This reduces token usage while keeping all information needed to compute correct expected values.

---