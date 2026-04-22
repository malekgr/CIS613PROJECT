"""
Token estimation and budget tracking for context chunking.

Uses tiktoken when available; falls back to a character-based heuristic
(~4 chars per token) that is accurate enough for budget enforcement.
"""
from __future__ import annotations

_CHARS_PER_TOKEN = 4  # conservative heuristic for Python code

# Approximate input-token prices in USD per 1 M tokens (as of 2025-04)
_PRICE_PER_M_INPUT: dict[str, float] = {
    "gemini-2.5-flash": 0.075,
    "gemini-2.5-pro":   1.25,
    "gemini-1.5-flash": 0.075,
    "gemini-1.5-pro":   1.25,
}
_DEFAULT_MODEL = "gemini-2.5-flash"


def estimate_tokens(text: str) -> int:
    """Estimate the number of LLM tokens in *text*."""
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_cost_usd(input_tokens: int, model: str = _DEFAULT_MODEL) -> float:
    """Return estimated API cost in USD for *input_tokens* tokens."""
    price = _PRICE_PER_M_INPUT.get(model, _PRICE_PER_M_INPUT[_DEFAULT_MODEL])
    return round(input_tokens * price / 1_000_000, 6)


class TokenBudget:
    """
    Tracks cumulative token usage against a fixed limit.

    Usage
    -----
    >>> budget = TokenBudget(limit=4000)
    >>> if budget.fits(some_code):
    ...     budget.consume(some_code)
    ...     include_in_prompt(some_code)
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._used = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return self.limit - self._used

    @property
    def utilization(self) -> float:
        """Fraction of budget used (0.0–1.0)."""
        return self._used / self.limit if self.limit else 0.0

    def fits(self, text: str) -> bool:
        """Return True if *text* fits within the remaining budget."""
        return self._used + estimate_tokens(text) <= self.limit

    def consume(self, text: str) -> bool:
        """
        Attempt to consume *text* against the budget.

        Returns True and increments usage if it fits; returns False otherwise.
        """
        tokens = estimate_tokens(text)
        if self._used + tokens <= self.limit:
            self._used += tokens
            return True
        return False

    def reset(self) -> None:
        self._used = 0
