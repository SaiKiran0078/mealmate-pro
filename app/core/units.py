"""Unit conversion.

Every quantity in the database is stored in the ingredient's *base unit*
(g, ml or pcs). This module converts what humans write ("2 tbsp", "1.5 kg")
into that base unit and back into something readable.
"""
from __future__ import annotations

from .models import Ingredient


class UnitError(ValueError):
    """Raised when a quantity cannot be converted for a given ingredient."""


_MASS = {"mg": 0.001, "g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592}
_VOLUME = {"ml": 1.0, "l": 1000.0, "tsp": 5.0, "tbsp": 15.0, "cup": 240.0}
_COUNT = {"pcs": 1.0}

_ALIASES = {
    "gram": "g", "grams": "g", "gm": "g",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "milligram": "mg", "milligrams": "mg",
    "milliliter": "ml", "millilitre": "ml", "milliliters": "ml", "millilitres": "ml",
    "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    "teaspoon": "tsp", "teaspoons": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbs": "tbsp", "tbl": "tbsp",
    "cups": "cup",
    "piece": "pcs", "pieces": "pcs", "pc": "pcs", "clove": "pcs", "cloves": "pcs",
    "slice": "pcs", "slices": "pcs", "whole": "pcs", "large": "pcs", "medium": "pcs",
    "small": "pcs", "unit": "pcs", "units": "pcs",
    "ounce": "oz", "ounces": "oz", "pound": "lb", "pounds": "lb", "lbs": "lb",
}


def normalize_unit(unit: str) -> str:
    u = (unit or "").strip().lower().rstrip(".")
    u = _ALIASES.get(u, u)
    if u not in _MASS and u not in _VOLUME and u not in _COUNT:
        raise UnitError(f"Unknown unit: {unit!r}")
    return u


def _kind(u: str) -> tuple[str, float]:
    if u in _MASS:
        return "mass", _MASS[u]
    if u in _VOLUME:
        return "volume", _VOLUME[u]
    return "count", _COUNT[u]


def _need_piece_weight(ing: Ingredient) -> float:
    if not ing.grams_per_piece:
        raise UnitError(f"'{ing.name}' has no known weight per piece, so pieces cannot be converted.")
    return ing.grams_per_piece


def to_base(amount: float, unit: str, ing: Ingredient) -> float:
    """Convert ``amount`` ``unit`` of ``ing`` into the ingredient's base unit."""
    if amount <= 0:
        raise UnitError("Quantity must be greater than zero.")
    kind, factor = _kind(normalize_unit(unit))
    base = ing.base_unit
    if (kind, base) in (("mass", "g"), ("volume", "ml"), ("count", "pcs")):
        return amount * factor  # same family: no conversion needed

    # Cross-family conversion goes through grams.
    if kind == "mass":
        grams = amount * factor
    elif kind == "volume":
        grams = amount * factor * ing.density_g_per_ml
    else:
        grams = amount * factor * _need_piece_weight(ing)

    if base == "g":
        return grams
    if base == "ml":
        return grams / ing.density_g_per_ml
    return grams / _need_piece_weight(ing)


def to_grams(qty_base: float, ing: Ingredient) -> float:
    """Weight in grams of ``qty_base`` (used for nutrition maths)."""
    if ing.base_unit == "g":
        return qty_base
    if ing.base_unit == "ml":
        return qty_base * ing.density_g_per_ml
    return qty_base * (ing.grams_per_piece or 0.0)


def _trim(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".rstrip("0").rstrip(".")


def format_quantity(qty: float, base_unit: str) -> str:
    """Human friendly text: 1500 g -> '1.5 kg', 0.5 pcs -> '0.5 pcs'."""
    if base_unit == "g":
        return f"{_trim(qty / 1000)} kg" if qty >= 1000 else f"{_trim(qty, 2)} g"
    if base_unit == "ml":
        return f"{_trim(qty / 1000)} l" if qty >= 1000 else f"{_trim(qty, 2)} ml"
    return f"{_trim(qty, 2)} pcs"
