"""Request bodies (Pydantic). Responses are plain dicts built in serializers.py."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    password: str = Field(min_length=8, max_length=128)


class ProfileIn(BaseModel):
    daily_kcal: int | None = Field(default=None, ge=800, le=6000)
    diet: str | None = Field(default=None, pattern=r"^(vegetarian|vegan|gluten_free|non_vegetarian)$")
    household_size: int = Field(default=1, ge=1, le=12)


class PantryIn(BaseModel):
    ingredient: str = Field(min_length=1, max_length=80, description="Ingredient name, e.g. 'spinach'")
    amount: float = Field(gt=0, le=100000)
    unit: str | None = Field(default=None, description="g, kg, ml, l, tsp, tbsp, cup, pcs. Defaults to the base unit.")
    expires_on: date | None = None


class PantryPatch(BaseModel):
    amount: float | None = Field(default=None, ge=0, le=100000, description="New remaining amount (0 marks it used up)")
    unit: str | None = None
    expires_on: date | None = None
    clear_expiry: bool = False


class RecipeIngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=100000)
    unit: str = "g"
    note: str = Field(default="", max_length=120)
    optional: bool = False


class StepIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=1000)
    duration_min: int | None = Field(default=None, ge=0, le=600)
    tip: str | None = Field(default=None, max_length=300)
    passive: bool = False


class RecipeIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    cuisine: str = Field(default="other", max_length=40)
    meal_types: list[str] = Field(min_length=1)
    servings: int = Field(ge=1, le=50)
    prep_min: int = Field(default=0, ge=0, le=600)
    cook_min: int = Field(default=0, ge=0, le=600)
    difficulty: str = Field(default="easy", pattern=r"^(easy|medium|hard)$")
    diet_tags: list[str] = []
    ingredients: list[RecipeIngredientIn] = Field(min_length=1)
    steps: list[StepIn] = Field(min_length=1)


class PlanIn(BaseModel):
    start_date: date | None = None
    days: int = Field(default=7, ge=1, le=14, description="1 = daily plan, 7 = weekly plan")
    meals: list[str] = Field(default_factory=lambda: ["breakfast", "lunch", "dinner"], description="Select at least one: breakfast, lunch, dinner, snack.")
    servings: int | None = Field(default=None, ge=1, le=12, description="Defaults to your household size")
    daily_kcal: int | None = Field(default=None, ge=800, le=6000)
    diet: str | None = Field(default=None, pattern=r"^(vegetarian|vegan|gluten_free|non_vegetarian)$")
    max_minutes: int | None = Field(default=None, ge=1, le=600)
    pantry_first: bool = True
    exclude_recipe_ids: list[int] = []
    max_repeats: int = Field(default=2, ge=1, le=5)
    save: bool = True

    @field_validator("meals")
    @classmethod
    def validate_meals(cls, meals: list[str]) -> list[str]:
        allowed = {"breakfast", "lunch", "dinner", "snack"}
        if not meals:
            raise ValueError("Choose at least one meal: breakfast, lunch, dinner, or snacks.")
        invalid = sorted(set(meals) - allowed)
        if invalid:
            raise ValueError("One of the selected meal types was not recognised. Please choose breakfast, lunch, dinner or snacks.")
        if len(set(meals)) != len(meals):
            raise ValueError("Each meal type can only be selected once.")
        return meals
