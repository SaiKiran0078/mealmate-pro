"""Turn "what we are short of" into a tidy shopping list."""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .matcher import recipe_needs
from .models import Ingredient, Recipe
from .stock import Stock, clone, consume
from .units import format_quantity


@dataclass(frozen=True)
class GroceryLine:
    ingredient_id: int
    name: str
    category: str
    quantity: float
    unit: str
    display: str

    def as_dict(self) -> dict:
        return {
            "ingredient_id": self.ingredient_id,
            "name": self.name,
            "category": self.category,
            "quantity": self.quantity,
            "unit": self.unit,
            "display": self.display,
        }


def round_up_for_shopping(qty: float, base_unit: str) -> float:
    """You cannot buy 37 g of rice: round up to a practical amount."""
    if base_unit == "pcs":
        return float(math.ceil(qty - 1e-9))
    step = 5 if qty < 100 else 10 if qty < 1000 else 50
    return float(math.ceil(qty / step - 1e-9) * step)


def build_grocery_list(shortfall: dict[int, float], ingredients: dict[int, Ingredient]) -> list[GroceryLine]:
    lines = []
    for ing_id, qty in shortfall.items():
        ing = ingredients[ing_id]
        rounded = round_up_for_shopping(qty, ing.base_unit)
        lines.append(
            GroceryLine(ing_id, ing.name, ing.category, rounded, ing.base_unit, format_quantity(rounded, ing.base_unit))
        )
    return sorted(lines, key=lambda line: (line.category, line.name))


def shortfall_for_meals(meals: Iterable[tuple[date, Recipe, int]], stock: Stock) -> dict[int, float]:
    """Replay meals in date order against a copy of the pantry; return what is missing."""
    sim = clone(stock)
    total: dict[int, float] = {}
    for on, recipe, servings in sorted(meals, key=lambda m: m[0]):
        result = consume(sim, recipe_needs(recipe, servings), on)
        for ing_id, qty in result.shortfall.items():
            total[ing_id] = total.get(ing_id, 0.0) + qty
    return total
