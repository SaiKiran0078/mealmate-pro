from datetime import date

import pytest

from app.core.matcher import eligible, evaluate, recipe_needs, suggest
from app.core.stock import Batch
from tests.factories import make_ing, make_recipe

D = date(2026, 10, 25)
RICE, EGG, SPINACH, SALT = make_ing(1, "rice"), make_ing(2, "egg", "pcs"), make_ing(3, "spinach"), make_ing(4, "salt", staple=True)
OMELETTE = make_recipe(1, "Omelette", [(EGG, 4), (SPINACH, 100), (SALT, 5), (RICE, 50, True)], meal_types=("breakfast",))
FRIED_RICE = make_recipe(2, "Fried rice", [(RICE, 300), (EGG, 2)])


def test_needs_skip_staples_optional_and_scale_with_servings():
    assert recipe_needs(OMELETTE) == {2: 4, 3: 100}
    assert recipe_needs(OMELETTE, servings=4) == {2: 8, 3: 200}


def test_full_pantry_means_can_cook_now():
    m = evaluate(OMELETTE, {2: [Batch(6)], 3: [Batch(150)]}, D)
    assert m.can_cook_now and m.coverage == 1.0 and m.missing == ()
    assert m.have_count == m.needed_count == 2


def test_partial_pantry_reports_exact_missing_amounts():
    m = evaluate(OMELETTE, {2: [Batch(4)], 3: [Batch(40)]}, D)
    assert not m.can_cook_now
    assert m.coverage == pytest.approx((1 + 0.4) / 2)
    assert [(x.ingredient.name, x.quantity) for x in m.missing] == [("spinach", 60)]


def test_expiring_food_raises_the_score():
    fresh = {2: [Batch(4)], 3: [Batch(100, date(2026, 12, 1))]}
    urgent = {2: [Batch(4)], 3: [Batch(100, date(2026, 10, 26))]}
    a, b = evaluate(OMELETTE, fresh, D), evaluate(OMELETTE, urgent, D)
    assert b.score > a.score
    assert [(e.ingredient.name, e.days_left) for e in b.expiring] == [("spinach", 1)]
    assert any("expires in 1 day" in r for r in b.reasons())


def test_ranking_prefers_the_recipe_the_pantry_covers():
    stock = {1: [Batch(300)], 2: [Batch(2)]}
    ranked = suggest([OMELETTE, FRIED_RICE], stock, D)
    assert [m.recipe.title for m in ranked] == ["Fried rice", "Omelette"]
    assert [m.recipe.title for m in suggest([OMELETTE, FRIED_RICE], stock, D, only_cookable=True)] == ["Fried rice"]


def test_filters():
    vegan = make_recipe(3, "Soup", [(RICE, 10)], diet_tags=("vegan",), prep_min=5, cook_min=10)
    assert eligible(vegan, diet="vegan") and not eligible(OMELETTE, diet="vegan")
    assert eligible(OMELETTE, meal_type="breakfast") and not eligible(OMELETTE, meal_type="dinner")
    assert eligible(vegan, max_minutes=15) and not eligible(vegan, max_minutes=14)
    assert not eligible(vegan, exclude_ids=[3])
