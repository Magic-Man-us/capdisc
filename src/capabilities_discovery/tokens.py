from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.functional_validators import AfterValidator

# Defined here, not imported from catalog/types.py: catalog/types.py itself imports
# token_bounds from this module, so importing back from it would be circular.
TokenCount = Annotated[
    int,
    Field(ge=0, title="Token count", description="Estimated token count of a text."),
]


def estimate_tokens(text: str) -> TokenCount:
    """Estimate a string's token count, cheaply and deterministically.

    ~4 chars/token with a word-count floor. A guard rail, not a billing figure — swap in
    tiktoken for a tighter number.

    Args:
        text: The text to estimate.

    Returns:
        The estimated token count.
    """
    return max(len(text) // 4, len(text.split()))


def token_bounds(max_tokens: TokenCount) -> AfterValidator:
    """Build an `AfterValidator` that rejects strings over a token estimate.

    Args:
        max_tokens: The inclusive upper bound on `estimate_tokens(value)`.

    Returns:
        A validator that returns the value unchanged, or raises `ValueError` when the estimate
        exceeds `max_tokens`.
    """

    def _check(value: str) -> str:
        used = estimate_tokens(value)
        if used > max_tokens:
            raise ValueError(f"~{used} tokens exceeds {max_tokens}-token maximum")
        return value

    return AfterValidator(_check)
