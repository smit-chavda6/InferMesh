"""Versioned static pricing table and per-request cost calculation.

Loaded once at startup from ``pricing.yaml`` (path configurable). This is a
point-in-time snapshot — provider prices drift and nothing here is fetched live.
Every request row stores the ``pricing_version`` it was costed against.

Model matching, most to least specific:
  1. exact model id
  2. model id with a trailing date suffix stripped (``-2026-04-23`` / ``-20260423``)
  3. longest ``models`` key that is a prefix of the model id
  4. the provider's ``default`` entry
  5. no match -> cost is ``None`` (row stores null costs, a warning is logged)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.logging_config import get_logger

log = get_logger(__name__)

_DATE_SUFFIX = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")
_CENT_MILLIONTH = Decimal("0.000001")  # 6dp, matches Numeric(12, 6) in the DB


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_1k: Decimal
    output_per_1k: Decimal
    estimated: bool = False


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal
    pricing_version: str
    matched_model: str
    estimated: bool


class PricingTable:
    def __init__(self, version: str, providers: dict[str, dict[str, Any]]) -> None:
        self.version = version
        self._providers = providers

    # -- loading -----------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> PricingTable:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "version" not in raw or "providers" not in raw:
            raise ValueError(f"pricing file {path} is missing 'version' or 'providers'")
        return cls(version=str(raw["version"]), providers=raw["providers"])

    # -- lookup ----------------------------------------------------------

    def _lookup(self, provider: str, model: str) -> tuple[ModelPrice, str] | None:
        pconf = self._providers.get(provider)
        if not pconf:
            return None
        models: dict[str, Any] = pconf.get("models", {}) or {}

        def _mk(entry: dict[str, Any]) -> ModelPrice:
            return ModelPrice(
                input_per_1k=Decimal(str(entry["input_per_1k"])),
                output_per_1k=Decimal(str(entry["output_per_1k"])),
                estimated=bool(entry.get("estimated", False)),
            )

        if model in models:
            return _mk(models[model]), model

        stripped = _DATE_SUFFIX.sub("", model)
        if stripped != model and stripped in models:
            return _mk(models[stripped]), stripped

        prefix_hits = [k for k in models if model.startswith(k)]
        if prefix_hits:
            best = max(prefix_hits, key=len)
            return _mk(models[best]), best

        if "default" in pconf:
            return _mk(pconf["default"]), f"{provider}:default"

        return None

    def cost(
        self, provider: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> CostBreakdown | None:
        hit = self._lookup(provider, model)
        if hit is None:
            log.warning("pricing.no_entry", provider=provider, model=model)
            return None
        price, matched = hit

        def _round(value: Decimal) -> Decimal:
            return value.quantize(_CENT_MILLIONTH, rounding=ROUND_HALF_UP)

        input_cost = _round(Decimal(prompt_tokens) / 1000 * price.input_per_1k)
        output_cost = _round(Decimal(completion_tokens) / 1000 * price.output_per_1k)
        return CostBreakdown(
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=_round(input_cost + output_cost),
            pricing_version=self.version,
            matched_model=matched,
            estimated=price.estimated,
        )


def _default_path() -> Path:
    # backend/app/pricing.py -> backend/pricing.yaml
    return Path(__file__).resolve().parent.parent / "pricing.yaml"


@lru_cache
def get_pricing_table(path: str | None = None) -> PricingTable:
    resolved = Path(path) if path else _default_path()
    table = PricingTable.from_file(resolved)
    log.info("pricing.loaded", version=table.version, path=str(resolved))
    return table
