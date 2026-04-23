from __future__ import annotations

import os
import time
from google import genai


_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 10

_MODEL_FALLBACK_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]


def _validate_syntax(code: str, attempt: int, max_retries: int) -> str:
    """Parse code for syntax errors; raise RuntimeError after final attempt."""
    import ast as _ast
    try:
        _ast.parse(code)
        return code
    except SyntaxError as syn:
        if attempt < max_retries:
            print(f"  [retry {attempt}/{max_retries}] Generated code has syntax error ({syn}), retrying…")
            return ""
        raise RuntimeError(f"LLM produced invalid Python after {max_retries} attempts: {syn}") from syn


def _is_overload_error(msg: str) -> bool:
    return "503" in msg or "429" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()


def _try_model(client, model: str, prompt: str) -> str:
    """Attempt generation on a single model with retries. Raises on persistent failure."""
    delay = _RETRY_BASE_DELAY
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            code = _validate_syntax(_sanitize(response.text.strip()), attempt, _MAX_RETRIES)
            if code:
                return code
        except RuntimeError:
            raise
        except Exception as exc:
            msg = str(exc)
            if attempt < _MAX_RETRIES and _is_overload_error(msg):
                print(f"  [retry {attempt}/{_MAX_RETRIES}] {model} unavailable, waiting {delay}s…")
                time.sleep(delay)
                delay *= 2
            else:
                raise
    return ""


def generate_tests(prompt: str, model: str = "gemini-2.5-flash-lite") -> str:
    """Send prompt to Gemini and return the generated test code.

    Tries the requested model first. If it is persistently unavailable (503/429),
    automatically falls back through _MODEL_FALLBACK_CHAIN before giving up.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    chain = [model] + [m for m in _MODEL_FALLBACK_CHAIN if m != model]
    last_exc: Exception | None = None

    for attempt_model in chain:
        try:
            result = _try_model(client, attempt_model, prompt)
            if result:
                if attempt_model != model:
                    print(f"  [fallback] succeeded with {attempt_model}")
                return result
        except RuntimeError:
            raise
        except Exception as exc:
            msg = str(exc)
            if _is_overload_error(msg):
                print(f"  [fallback] {attempt_model} still unavailable, trying next model…")
                last_exc = exc
                continue
            raise

    raise RuntimeError(
        f"All models unavailable after fallback chain {chain}. Last error: {last_exc}"
    ) from last_exc


def _sanitize(code: str) -> str:
    """Strip control characters and markdown fences from LLM output."""
    import re
    code = re.sub(r"^```[^\n]*\n?", "", code, flags=re.MULTILINE)
    code = re.sub(r"```$", "", code, flags=re.MULTILINE)
    code = re.sub(r"[^\x09\x0a\x0d\x20-\x7e]", "", code)
    code = code.replace("\x7f", "")
    return code.strip()
