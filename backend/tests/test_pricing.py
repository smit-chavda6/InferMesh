"""Pricing table: model matching precedence and cost math."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing import PricingTable, get_pricing_table

_TABLE = PricingTable(
    version="test-1",
    providers={
        "openai": {
            "default": {"input_per_1k": 0.001, "output_per_1k": 0.002},
            "models": {
                "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
                "gpt-5.4": {"input_per_1k": 0.00125, "output_per_1k": 0.01, "estimated": True},
            },
        }
    },
)


def test_exact_model_match() -> None:
    cost = _TABLE.cost("openai", "gpt-4o-mini", 1000, 1000)
    assert cost is not None
    assert cost.input_cost_usd == Decimal("0.000150")
    assert cost.output_cost_usd == Decimal("0.000600")
    assert cost.total_cost_usd == Decimal("0.000750")
    assert cost.pricing_version == "test-1"
    assert cost.matched_model == "gpt-4o-mini"
    assert cost.estimated is False


def test_date_suffix_is_stripped_before_matching() -> None:
    cost = _TABLE.cost("openai", "gpt-4o-mini-2024-07-18", 2000, 0)
    assert cost is not None
    assert cost.matched_model == "gpt-4o-mini"
    assert cost.input_cost_usd == Decimal("0.000300")


def test_prefix_match_when_no_exact() -> None:
    cost = _TABLE.cost("openai", "gpt-5.4-preview-x", 1000, 0)
    assert cost is not None
    assert cost.matched_model == "gpt-5.4"
    assert cost.estimated is True


def test_falls_back_to_provider_default() -> None:
    cost = _TABLE.cost("openai", "some-unknown-model", 1000, 1000)
    assert cost is not None
    assert cost.matched_model == "openai:default"
    assert cost.total_cost_usd == Decimal("0.003000")


def test_unknown_provider_returns_none() -> None:
    assert _TABLE.cost("cohere", "command-r", 100, 100) is None


def test_provider_without_default_and_no_match_returns_none() -> None:
    table = PricingTable(
        version="x",
        providers={
            "gemini": {"models": {"gemini-3.6-flash": {"input_per_1k": 1, "output_per_1k": 1}}}
        },
    )
    assert table.cost("gemini", "nonexistent", 10, 10) is None


def test_rounding_to_six_places() -> None:
    cost = _TABLE.cost("openai", "gpt-4o-mini", 11, 7)
    assert cost is not None
    # 11/1000 * 0.00015 = 0.00000165 -> 0.000002 ; 7/1000 * 0.0006 = 0.0000042 -> 0.000004
    assert cost.input_cost_usd == Decimal("0.000002")
    assert cost.output_cost_usd == Decimal("0.000004")


def test_shipped_pricing_yaml_loads_and_covers_live_models() -> None:
    table = get_pricing_table()
    assert table.version
    for provider, model in [
        ("openai", "gpt-5.4"),
        ("gemini", "gemini-3.6-flash"),
        ("anthropic", "claude-3-5-sonnet-latest"),
    ]:
        cost = table.cost(provider, model, 1000, 1000)
        assert cost is not None, f"{provider}/{model} has no price"
        assert cost.total_cost_usd > 0


@pytest.mark.parametrize("missing", ["version", "providers"])
def test_from_file_rejects_incomplete_file(tmp_path, missing: str) -> None:
    data = {"version": "1", "providers": {}}
    del data[missing]
    p = tmp_path / "bad.yaml"
    import yaml

    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        PricingTable.from_file(p)
