"""Tests for the model pricing table and cost estimator (backend/utils/pricing.py)."""

import pytest

from utils.pricing import PRICING_PER_1M, estimate_cost

# Every priced model, with the exact per-1M (input, output) USD pair the table must hold.
#
# Relative assertions (`> 0`, `mini < full`) cannot catch a decimal point in the wrong
# place, and these numbers are cost-facing: an operator reads the dashboard's cost column
# as real money, so a 10x typo is a 10x wrong invoice estimate. Pinning the exact pairs
# makes an accidental edit fail loudly; a deliberate repricing updates both sides together.
EXPECTED_PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4": (3.0, 15.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-haiku": (1.0, 5.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4o": (2.5, 10.0),
    "gpt-4-turbo": (10.0, 30.0),
    "gemini-1.5-flash": (0.075, 0.3),
    "gemini-1.5-pro": (1.25, 5.0),
    "gemini-2.0-flash": (0.1, 0.4),
    "default": (0.0, 0.0),
}


def test_pricing_table_holds_exactly_the_expected_models() -> None:
    """A model added to (or dropped from) the table without a price review fails here."""
    assert set(PRICING_PER_1M) == set(EXPECTED_PRICES)


@pytest.mark.parametrize("model", sorted(EXPECTED_PRICES))
def test_pricing_table_entry_is_exact(model: str) -> None:
    assert PRICING_PER_1M[model] == EXPECTED_PRICES[model]


@pytest.mark.parametrize("model", sorted(set(EXPECTED_PRICES) - {"default"}))
def test_estimate_cost_charges_the_table_price(model: str) -> None:
    """The estimator has to bill what the table says, for input and output separately.

    Asymmetric token counts so a lookup that swapped the two prices can't produce the
    same total as the correct one.
    """
    in_price, out_price = EXPECTED_PRICES[model]

    cost = estimate_cost(model, input_tokens=2_000_000, output_tokens=1_000_000)

    assert cost == pytest.approx(2 * in_price + out_price)


@pytest.mark.parametrize("model", sorted(set(EXPECTED_PRICES) - {"default"}))
def test_dated_model_variants_resolve_to_their_base_price(model: str) -> None:
    """Prefix matching is what lets `claude-sonnet-4-20250514` bill as `claude-sonnet-4`."""
    in_price, out_price = EXPECTED_PRICES[model]

    cost = estimate_cost(f"{model}-20250514", input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost == pytest.approx(in_price + out_price)


def test_gemini_model_yields_non_zero_cost() -> None:
    """Before the fix, any Gemini model fell through to the `default` (0.0, 0.0)
    entry and every Gemini site reported $0.00 cost regardless of usage."""

    cost = estimate_cost("gemini-1.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost > 0.0


def test_unpriced_model_still_falls_back_to_default_zero() -> None:
    """A model with no matching entry (e.g. a local Ollama model) should still
    resolve to the explicit `default` (0.0, 0.0) rather than raising."""

    assert estimate_cost("llama3", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0


def test_longest_prefix_match_prefers_gpt_4o_mini_over_gpt_4o() -> None:
    """`gpt-4o-mini` must resolve to the mini price, not the (shorter-prefix)
    `gpt-4o` price — this is the longest-prefix-match property the lookup relies on."""

    mini_cost = estimate_cost("gpt-4o-mini-2024-07-18", input_tokens=1_000_000, output_tokens=1_000_000)
    full_cost = estimate_cost("gpt-4o-2024-08-06", input_tokens=1_000_000, output_tokens=1_000_000)

    assert mini_cost > 0.0
    assert full_cost > 0.0
    assert mini_cost != full_cost
    assert mini_cost < full_cost
