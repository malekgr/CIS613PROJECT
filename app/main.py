"""
app/main.py — FastAPI backend for the LLM Test Generator UI.

Run from the project root:
    GEMINI_API_KEY=... python3 -m uvicorn app.main:app --reload --port 8000
"""
import ast
import asyncio
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from src.pipeline import run_pipeline
from src.report_generator import (
    _flatten,
    compute_mode_summary,
    generate_markdown,
    save_category_summary_csv,
    save_csv,
    save_failure_summary,
    save_json,
    save_mode_summary_csv,
)

app = FastAPI(title="LLM Test Generator")

JOBS_DIR = ROOT / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

_ALL_RESULTS_FILE  = "all_results.json"
_UPLOADED_MODULE   = "uploaded_module.py"
_DOWNLOAD_FILES = [
    "results_table.csv",
    "mode_summary.csv",
    "category_summary.csv",
    "failure_summary.json",
    "report.md",
    _ALL_RESULTS_FILE,
]

_jobs: dict = {}  # in-memory cache; disk is the source of truth


# ---------------------------------------------------------------------------
# Disk persistence — survives server restarts
# ---------------------------------------------------------------------------

def _state_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "state.json"


def _save_state(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    # Omit results — rebuilt from the output file on load
    safe = {k: v for k, v in job.items() if k != "results"}
    safe["results"] = None
    _state_path(job_id).write_text(json.dumps(safe, indent=2), encoding="utf-8")


def _load_state(job_id: str) -> dict:
    path = _state_path(job_id)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") == "done" and data.get("results") is None:
        results_file = JOBS_DIR / job_id / "output" / _ALL_RESULTS_FILE
        if results_file.exists():
            all_results = json.loads(results_file.read_text(encoding="utf-8"))
            data["results"] = _summarise(all_results)
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


def _extract_public_callables(tree: ast.Module) -> list:
    """Return public names. Top-level functions as 'name'; class methods as 'Class.name'."""
    callables = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            callables.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    callables.append(f"{node.name}.{item.name}")
    return callables


@app.post("/api/parse")
async def parse_file(file: UploadFile):
    content = await file.read()
    try:
        tree = ast.parse(content.decode("utf-8"))
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"SyntaxError: {exc}") from exc
    functions = _extract_public_callables(tree)
    return {"filename": file.filename, "functions": functions}


@app.post("/api/generate")
async def generate(
    file: UploadFile,
    modes: str = Form(...),
    background_tasks: BackgroundTasks = None,
):
    content = await file.read()
    try:
        tree = ast.parse(content.decode("utf-8"))
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    functions = _extract_public_callables(tree)
    if not functions:
        raise HTTPException(status_code=400, detail="No public functions found.")

    mode_list = [m.strip() for m in modes.split(",") if m.strip()]
    if not mode_list:
        raise HTTPException(status_code=400, detail="Select at least one mode.")

    job_id  = str(uuid.uuid4())[:8]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()
    (job_dir / _UPLOADED_MODULE).write_bytes(content)
    (job_dir / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n",
        encoding="utf-8",
    )

    _jobs[job_id] = {
        "status": "running", "log": [],
        "functions": functions, "modes": mode_list,
        "results": None, "error": None,
    }
    _save_state(job_id)

    background_tasks.add_task(_run_job, job_id, job_dir, functions, mode_list)
    return {"job_id": job_id, "functions": functions}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    print("GET job:", job_id, "state exists:", _state_path(job_id).exists())
    job = _jobs.get(job_id) or _load_state(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job_id not in _jobs:
        _jobs[job_id] = job
    return JSONResponse(content=job)


@app.post("/api/chunk-preview", responses={400: {"description": "Invalid target, chunk mode, or file"}})
async def chunk_preview(
    file: UploadFile,
    target: str = Form(...),
    chunk_mode: str = Form(...),
):
    """Assemble and return a ChunkContext for any uploaded file — no LLM call."""
    from src.chunker import ChunkMode, SmartChunker
    content = await file.read()

    def _build():
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
            tf.write(content)
            tmp = Path(tf.name)
        try:
            return SmartChunker(str(tmp)).build(
                target, ChunkMode(chunk_mode), import_path="uploaded_module"
            )
        finally:
            tmp.unlink(missing_ok=True)

    try:
        chunk = await asyncio.to_thread(_build)
        return JSONResponse(_serialise_chunk(chunk))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/chunk-preview", responses={400: {"description": "Invalid target or chunk mode"}, 404: {"description": "Job source file not found"}})
async def job_chunk_preview(
    job_id: str,
    target: str = Form(...),
    chunk_mode: str = Form(...),
):
    """Assemble a ChunkContext using the already-uploaded file for a completed job."""
    from src.chunker import ChunkMode, SmartChunker
    source = JOBS_DIR / job_id / _UPLOADED_MODULE
    if not source.exists():
        raise HTTPException(status_code=404, detail="Job source file not found.")
    try:
        chunk = SmartChunker(str(source)).build(
            target, ChunkMode(chunk_mode), import_path="uploaded_module"
        )
        return JSONResponse(_serialise_chunk(chunk))
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _serialise_chunk(chunk) -> dict:
    return {
        "target":            chunk.target,
        "function_name":     chunk.function_name,
        "class_name":        chunk.class_name,
        "mode_used":         chunk.mode_used.value,
        "tokens_used":       chunk.tokens_used,
        "cost_estimate_usd": chunk.cost_estimate_usd,
        "imports":           chunk.imports or "",
        "class_header":      chunk.class_header or "",
        "target_source":     chunk.target_source or "",
        "dependency_sources": chunk.dependency_sources or [],
        "summary_context":   chunk.summary_context or "",
    }


@app.get("/api/jobs/{job_id}/files/{filename}")
async def download_file(job_id: str, filename: str):
    path = JOBS_DIR / job_id / "output" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, filename=filename)


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------

def _log(job_id: str, msg: str) -> None:
    _jobs[job_id]["log"].append(msg)
    _save_state(job_id)


def _run_job(job_id: str, job_dir: Path, functions: list, modes: list) -> None:
    source_file = str(job_dir / _UPLOADED_MODULE)
    output_dir  = job_dir / "output"
    output_dir.mkdir(exist_ok=True)

    all_results: dict = {}
    total = len(functions) * len(modes)
    done  = 0

    try:
        for func in functions:
            all_results[func] = {}
            for mode in modes:
                done += 1
                _log(job_id, f"[{done}/{total}] {func} · {mode} — generating tests…")
                try:
                    result = run_pipeline(
                        source_file=source_file,
                        function_name=func,
                        project_root=str(job_dir),
                        mode=mode,
                        verbose=False,
                        import_path="uploaded_module",
                        cov_target="uploaded_module",
                        chunking_mode="class_context" if "." in func else "function_plus_deps",
                        log_callback=lambda msg: _log(job_id, msg),
                    )
                    all_results[func][mode] = result
                    passed = result.get("passed_count") or 0
                    total_ = result.get("total_count") or 0
                    rate   = result.get("execution_success_rate") or 0
                    _log(job_id, f"  \u2713 {passed}/{total_} passed ({rate*100:.0f}%)")
                except Exception as exc:
                    _log(job_id, f"  \u2717 error: {exc}")
                    all_results[func][mode] = {"error": str(exc)}

        _log(job_id, "Saving outputs…")
        save_json(all_results,                 str(output_dir / _ALL_RESULTS_FILE))
        save_csv(all_results,                  str(output_dir / "results_table.csv"))
        save_mode_summary_csv(all_results,     str(output_dir / "mode_summary.csv"))
        save_category_summary_csv(all_results, str(output_dir / "category_summary.csv"))
        save_failure_summary(all_results,      str(output_dir / "failure_summary.json"))
        generate_markdown(all_results,         str(output_dir / "report.md"))

        _jobs[job_id]["results"] = _summarise(all_results)
        _jobs[job_id]["status"]  = "done"
        _log(job_id, "Done.")

    except Exception as exc:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"]  = str(exc)
        _log(job_id, f"Fatal error: {exc}")


def _summarise(all_results: dict) -> dict:
    failures = [
        {
            "function": fn,
            "mode":     mode,
            "test":     f.get("test_name", ""),
            "category": f.get("category", ""),
            "detail":   f.get("detail", ""),
        }
        for fn, modes in all_results.items()
        for mode, mode_data in modes.items()
        for f in mode_data.get("failures", [])
    ]
    return {
        "mode_summary": compute_mode_summary(all_results),
        "per_function": _flatten(all_results),
        "failures":     failures,
        "downloads":    _DOWNLOAD_FILES,
    }
