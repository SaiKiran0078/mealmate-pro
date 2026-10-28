from datetime import date

import pytest

from app.core.cooking_guide import build_guide
from app.core.grocery import build_grocery_list, round_up_for_shopping
from app.core.models import Nutrition
from app.core.nutrition import macro_split, progress_against_target, recipe_nutrition
from app.core.stock import Batch
from tests.factories import make_ing

D = date(2026, 10, 25)


@pytest.mark.parametrize(
    "qty, unit, expected", [(37, "g", 40), (12, "g", 15), (230, "g", 230), (231, "g", 240), (1020, "g", 1050), (1.2, "pcs", 2), (3, "pcs", 3)]
)
def test_round_up_for_shopping(qty, unit, expected):
    assert round_up_for_shopping(qty, unit) == expected


def test_grocery_list_is_sorted_by_aisle_then_name():
    ings = {1: make_ing(1, "tofu", category="protein"), 2: make_ing(2, "apple", "pcs", category="produce"),
            3: make_ing(3, "carrot", "pcs", category="produce")}
    lines = build_grocery_list({1: 301, 2: 1.2, 3: 3}, ings)
    assert [(line.category, line.name) for line in lines] == [("produce", "apple"), ("produce", "carrot"), ("protein", "tofu")]
    assert [line.display for line in lines] == ["2 pcs", "3 pcs", "310 g"]


def test_recipe_nutrition_per_serving_and_missing_data_flag(conn, catalog):
    recipes, _ = catalog
    omelette = recipes["Masala Omelette"]
    n, complete = recipe_nutrition(omelette.ingredients, omelette.servings)
    assert complete and 150 < n.kcal < 260 and n.protein > 10

    unknown = make_ing(9, "mystery", nutrition_known=False)
    from app.core.models import RecipeIngredient

    _, complete = recipe_nutrition([RecipeIngredient(unknown, 100)], 1)
    assert complete is False


def test_macro_split_adds_up_to_100():
    split = macro_split(Nutrition(kcal=0, protein=50, carbs=100, fat=30))
    assert sum(split.values()) == pytest.approx(100, abs=0.2)
    assert macro_split(Nutrition())["protein_pct"] == 0.0


def test_progress_against_target():
    out = progress_against_target(Nutrition(kcal=1500, protein=80, carbs=150, fat=50), 2000)
    assert out["percent_of_target"] == 75 and out["totals"]["kcal"] == 1500


def test_guide_marks_missing_items_and_suggests_swaps(catalog):
    recipes, ings = catalog
    curry = recipes["Chickpea Spinach Curry"]
    stock = {ings["chickpeas"].id: [Batch(400)], ings["onion"].id: [Batch(2)], ings["garlic"].id: [Batch(5)],
             ings["canned tomatoes"].id: [Batch(400)]}
    guide = build_guide(curry, stock, D)
    status = {i.name: i.status for i in guide.ingredients}
    assert status["chickpeas"] == "in_pantry" and status["spinach"] == "missing" and status["salt"] == "staple"
    assert guide.missing == ["spinach"] and not guide.can_cook_now
    assert "spinach" in guide.substitutions
    assert any("chopped" in line.lower() or "minced" in line.lower() for line in guide.mise_en_place)


def test_guide_timeline_and_scaling(catalog):
    recipes, _ = catalog
    soup = recipes["Red Lentil Soup"]
    guide = build_guide(soup, {}, D, servings=6)
    assert guide.servings == 6
    assert [s.number for s in guide.steps] == list(range(1, len(soup.steps) + 1))
    starts = [s.starts_at_min for s in guide.steps]
    assert starts == sorted(starts) and starts[0] == 0
    lentils = next(i for i in guide.ingredients if i.name == "red lentils")
    assert lentils.quantity == "400 g"  # recipe is for 3, we asked for 6
