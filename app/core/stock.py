"""Pantry stock model with expiry-aware consumption (first-expiring-first-out)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

EPS = 1e-9


@dataclass
class Batch:
    """One purchase of an ingredient. The same ingredient can have many batches."""

    qty: float
    expires_on: date | None = None
    pantry_id: int | None = None  # row id in the database (None in simulations)


Stock = dict[int, list[Batch]]  # ingredient_id -> batches


@dataclass
class ConsumeResult:
    shortfall: dict[int, float] = field(default_factory=dict)  # ingredient_id -> amount we lacked
    deductions: list[tuple[int | None, float]] = field(default_factory=list)  # (pantry_id, amount)


def clone(stock: Stock) -> Stock:
    return {k: [replace(b) for b in v] for k, v in stock.items()}


def usable(batch: Batch, on: date) -> bool:
    return batch.qty > EPS and (batch.expires_on is None or batch.expires_on >= on)


def available(stock: Stock, ingredient_id: int, on: date) -> float:
    return sum(b.qty for b in stock.get(ingredient_id, []) if usable(b, on))


def consume(stock: Stock, needs: dict[int, float], on: date) -> ConsumeResult:
    """Take ``needs`` out of ``stock`` (mutates it), earliest expiry first.

    Anything that cannot be covered is reported in ``shortfall``.
    """
    result = ConsumeResult()
    for ingredient_id, need in needs.items():
        remaining = need
        batches = sorted(
            (b for b in stock.get(ingredient_id, []) if usable(b, on)),
            key=lambda b: (b.expires_on is None, b.expires_on or date.max),
        )
        for batch in batches:
            if remaining <= EPS:
                break
            take = min(batch.qty, remaining)
            batch.qty -= take
            remaining -= take
            result.deductions.append((batch.pantry_id, take))
        if remaining > EPS:
            result.shortfall[ingredient_id] = remaining
    return result
