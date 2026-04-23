from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.chunker import ChunkContext


def build_chunked_prompt(chunk: "ChunkContext") -> str:
    """Build an LLM prompt from a ChunkContext produced by SmartChunker."""
    name = chunk.function_name
    import_path = chunk.import_path or "module"
    target_label = chunk.target  # may be "Class.method" or "function"

    parts: list[str] = []

    if chunk.imports:
        parts.append(f"# Module imports:\n{chunk.imports}")
    if chunk.class_header:
        parts.append(f"# Class context:\n{chunk.class_header}")
    parts.append(f"# Target function/method:\n{chunk.target_source}")
    if chunk.dependency_sources:
        dep_block = "\n\n".join(chunk.dependency_sources)
        parts.append(f"# Helper functions used by the target:\n{dep_block}")
    if chunk.summary_context:
        parts.append(chunk.summary_context)

    code_block = "\n\n".join(parts)
    context_section = f"""## Source Context
```python
{code_block}
```
"""

    if chunk.class_name:
        import_line = f"from {import_path} import {chunk.class_name}"
        instantiation_hint = (
            f"- Instantiate the class in each test or a pytest fixture: "
            f"`service = {chunk.class_name}()`\n"
            f"- Call the method as `service.{name}(...)` — do NOT import `{name}` directly"
        )
    else:
        import_line = f"from {import_path} import {name}"
        instantiation_hint = ""

    prompt = f"""You are an expert Python software tester.

Your task is to write comprehensive PyTest unit tests for `{target_label}`.

{context_section}
## Requirements
- Write tests using `pytest` (plain functions, no classes required)
- Import line: `{import_line}`
{instantiation_hint}
- Cover: normal cases, edge cases, and boundary/invalid inputs
- Each test function must have a clear, descriptive name (e.g. `test_{name}_basic`)
- Do NOT use `pytest-mock` or the `mocker` fixture — it is NOT installed.
  Use `unittest.mock.patch` or `unittest.mock.MagicMock` if mocking is needed.
- Do NOT import or use any external libraries beyond `pytest` and `unittest.mock`
- Do NOT modify the source function
- Every expected output must be explicitly justified by the provided context.
  Read the source carefully: compute expected values by tracing the exact code logic,
  not by guessing or applying shortcuts (e.g. pay attention to WHEN tax/discounts are applied).
- Only assert keys that are explicitly present in the function's return statement.
  Do NOT assert keys you invent or assume — check the actual return dict in the source.
- For floating-point comparisons use `pytest.approx()` (e.g. `assert result == pytest.approx(84.0)`)
- Add a one-line comment on each test explaining what it verifies

## Output Format
Return ONLY the Python test code. No explanation, no markdown fences, no extra text.
Start directly with the import statement.
"""
    return prompt


def build_prompt(context: dict, import_path: str = "dataset.sample_functions") -> str:
    name = context["name"]
    source = context["source"]

    spec_section = f"""## Function Source Code
```python
{source}
```
"""

    prompt = f"""You are an expert Python software tester.

Your task is to write comprehensive PyTest unit tests for the following Python function.

{spec_section}
## Requirements
- Write tests using `pytest` (plain functions, no classes required)
- Import the function at the top: `from {import_path} import {name}`
- Cover: normal cases, edge cases, and boundary/invalid inputs
- Each test function must have a clear, descriptive name (e.g. `test_{name}_equilateral`)
- Do NOT use `pytest-mock` or the `mocker` fixture — it is NOT installed.
  Use `unittest.mock.patch` or `unittest.mock.MagicMock` if mocking is needed.
- Do NOT import or use any external libraries beyond `pytest` and `unittest.mock`
- Do NOT modify the source function
- Every expected output must be explicitly justified by the specification — trace the exact code logic
- For floating-point comparisons use `pytest.approx()`
- Only assert keys that are explicitly present in the function's return statement
- Add a one-line comment on each test explaining what it verifies

## Output Format
Return ONLY the Python test code. No explanation, no markdown fences, no extra text.
Start directly with the import statement.
"""
    return prompt
