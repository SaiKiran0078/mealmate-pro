"""Plain data classes shared by the whole engine (no database, no web code)."""
from __future__ import annotations

from dataclasses import dataclass

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
DIETS = ("vegetarian", "vegan", "gluten_free", "non_vegetarian")


@dataclass(frozen=True)
class User:
    id: int
    email: str
    daily_kcal: int | None = None
    diet: str | None = None
    household_size: int = 1


@dataclass(frozen=True)
class Ingredient:
    id: int
    name: str
    base_unit: str  # "g", "ml" or "pcs" - every quantity is stored in this unit
    category: str = "other"
    is_staple: bool = False  # salt, oil, spices: assumed to always be in the kitchen
    density_g_per_ml: float = 1.0
    grams_per_piece: float | None = None
    kcal_per_100g: float = 0.0
    protein_per_100g: float = 0.0
    carbs_per_100g: float = 0.0
    fat_per_100g: float = 0.0
    nutrition_known: bool = True


@dataclass(frozen=True)
class Nutrition:
    kcal: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0

    def __add__(self, other: Nutrition) -> Nutrition:
        return Nutrition(
            self.kcal + other.kcal,
            self.protein + other.protein,
            self.carbs + other.carbs,
            self.fat + other.fat,
        )

    def scaled(self, factor: float) -> Nutrition:
        return Nutrition(self.kcal * factor, self.protein * factor, self.carbs * factor, self.fat * factor)

    def as_dict(self) -> dict:
        return {
            "kcal": round(self.kcal),
            "protein_g": round(self.protein, 1),
            "carbs_g": round(self.carbs, 1),
            "fat_g": round(self.fat, 1),
        }


@dataclass(frozen=True)
class RecipeIngredient:
    ingredient: Ingredient
    quantity: float  # in the ingredient's base unit
    note: str = ""  # e.g. "finely chopped"
    optional: bool = False


@dataclass(frozen=True)
class RecipeStep:
    number: int
    instruction: str
    duration_min: int | None = None
    tip: str | None = None
    passive: bool = False  # simmering, resting, baking: your hands are free


@dataclass(frozen=True)
class Recipe:
    id: int
    title: str
    servings: int
    meal_types: tuple[str, ...]
    ingredients: tuple[RecipeIngredient, ...]
    description: str = ""
    cuisine: str = "other"
    prep_min: int = 0
    cook_min: int = 0
    difficulty: str = "easy"
    diet_tags: tuple[str, ...] = ()
    steps: tuple[RecipeStep, ...] = ()
    nutrition_per_serving: Nutrition = Nutrition()
    nutrition_complete: bool = True
    source: str = "user"
    image_url: str | None = None

    @property
    def total_min(self) -> int:
        return self.prep_min + self.cook_min
