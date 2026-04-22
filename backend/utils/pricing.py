"""Model pricing table and cost estimator for token-usage tracking.

Prices are per 1,000,000 tokens (USD), as (input, output) tuples. Prefix match
lets us catch dated variants (e.g. claude-sonnet-4-20250514 matches claude-sonnet-4).
"""

PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4": (3.0, 15.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-haiku": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "default": (0.0, 0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for a completion. Matches `model` against PRICING_PER_1M
    by longest case-insensitive prefix, falling back to the `default` entry."""
    if not model:
        in_price, out_price = PRICING_PER_1M["default"]
    else:
        lowered = model.lower()
        # Longest prefix wins — "gpt-4o-mini" must beat "gpt-4o".
        best: tuple[float, float] | None = None
        best_len = -1
        for prefix, pair in PRICING_PER_1M.items():
            if prefix == "default":
                continue
            if lowered.startswith(prefix.lower()) and len(prefix) > best_len:
                best = pair
                best_len = len(prefix)
        in_price, out_price = best if best is not None else PRICING_PER_1M["default"]
    return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
