from datetime import date, timedelta

import pytest

from app.core.grocery import shortfall_for_meals
from app.core.planner import PlanRequest, generate_plan
from app.core.stock import Batch
from app.repositories import ingredients as ingredient_repo
from app.repositories import recipes as recipe_repo

START = date(2026, 10, 26)


def _plan(conn, stock=None, **kw):
    recipes = recipe_repo.load_recipes(conn, None)
    ings = ingredient_repo.load_all(conn)
    return generate_plan(recipes, stock or {}, PlanRequest(start=START, **kw), ings), ings


def test_weekly_plan_shape(conn):
    plan, _ = _plan(conn, days=7)
    assert len(plan.days) == 7
    assert [d.day for d in plan.days] == [START + timedelta(days=i) for i in range(7)]
    assert all([m.meal_type for m in d.meals] == ["breakfast", "lunch", "dinner"] for d in plan.days)
    assert plan.grocery, "an empty pantry must produce a shopping list"
    assert all(line.quantity > 0 for line in plan.grocery)


def test_plan_is_deterministic(conn):
    a, _ = _plan(conn, days=7)
    b, _ = _plan(conn, days=7)
    assert [m.recipe.id for m in a.meals()] == [m.recipe.id for m in b.meals()]


def test_recipes_do_not_repeat_more_than_allowed(conn):
    plan, _ = _plan(conn, days=7, max_repeats=2)
    counts: dict[int, int] = {}
    for m in plan.meals():
        counts[m.recipe.id] = counts.get(m.recipe.id, 0) + 1
    assert max(counts.values()) <= 2


def test_pantry_drives_the_choice_and_empties_the_shopping_list(conn, catalog):
    recipes, ings = catalog
    soup = recipes["Red Lentil Soup"]
    stock = {
        ings["red lentils"].id: [Batch(400)], ings["onion"].id: [Batch(3)], ings["garlic"].id: [Batch(10)],
        ings["carrot"].id: [Batch(4)], ings["lemon"].id: [Batch(2)],
    }
    plan, _ = _plan(conn, stock, days=1, meals=("dinner",))
    assert plan.days[0].meals[0].recipe.id == soup.id
    assert plan.days[0].meals[0].coverage == 1.0
    assert plan.shortfall == {} and plan.grocery == []


def test_pantry_is_not_spent_twice(conn, catalog):
    """Pantry holds lentils for ONE full soup (3 servings). Cooking two soups must leave
    the second one uncovered, so exactly one soup's worth of lentils goes on the shopping list."""
    recipes, ings = catalog
    stock = {i: [Batch(100)] for i in (ings["onion"].id, ings["garlic"].id, ings["carrot"].id, ings["lemon"].id)}
    stock[ings["red lentils"].id] = [Batch(200)]
    others = frozenset(r.id for title, r in recipes.items() if title != "Red Lentil Soup")
    plan, _ = _plan(conn, stock, days=2, meals=("dinner",), servings=3, max_repeats=2, exclude_recipe_ids=others)
    assert [m.recipe.title for m in plan.meals()] == ["Red Lentil Soup", "Red Lentil Soup"]
    assert plan.days[0].meals[0].missing == ()       # first soup is fully covered
    assert plan.days[1].meals[0].missing != ()       # second soup is not
    assert plan.shortfall[ings["red lentils"].id] == pytest.approx(200)


def test_plan_shortfall_matches_replaying_the_meals(conn, catalog):
    _, ings = catalog
    stock = {ings["egg"].id: [Batch(6, START + timedelta(days=2))], ings["rice"].id: [Batch(500)],
             ings["chicken breast"].id: [Batch(300)]}
    plan, _ = _plan(conn, stock, days=3, servings=2)
    replay = shortfall_for_meals([(m.day, m.recipe, m.servings) for m in plan.meals()], stock)
    assert replay.keys() == plan.shortfall.keys()
    for k, v in replay.items():
        assert v == pytest.approx(plan.shortfall[k])


def test_staples_never_reach_the_shopping_list(conn):
    plan, _ = _plan(conn, days=7)
    assert not {"salt", "olive oil", "cumin", "turmeric"} & {line.name for line in plan.grocery}


def test_expiring_pantry_item_is_used_first(conn, catalog):
    _, ings = catalog
    # Lots of tofu so coverage is similar, but only the broccoli is about to expire.
    stock = {ings["broccoli"].id: [Batch(300, START)]}
    plan, _ = _plan(conn, stock, days=1, meals=("dinner",))
    meal = plan.days[0].meals[0]
    assert "broccoli" in meal.uses_expiring


def test_unused_expiring_food_triggers_a_warning(conn, catalog):
    _, ings = catalog
    stock = {ings["cucumber"].id: [Batch(2, START)]}  # no breakfast recipe uses cucumber
    plan, _ = _plan(conn, stock, days=1, meals=("breakfast",))
    assert any("cucumber" in w and "not used" in w for w in plan.warnings)


def test_vegan_plan_only_contains_vegan_recipes(conn):
    plan, _ = _plan(conn, days=3, diet="vegan")
    assert plan.meals() and all("vegan" in m.recipe.diet_tags for m in plan.meals())


def test_impossible_filters_produce_warnings_not_crashes(conn):
    plan, _ = _plan(conn, days=2, meals=("snack",), diet="vegan", max_repeats=1)
    assert plan.days  # the plan still exists
    assert plan.warnings


def test_calorie_target_moves_the_average(conn):
    low, _ = _plan(conn, days=7, daily_kcal=1400)
    high, _ = _plan(conn, days=7, daily_kcal=2800)
    assert low.average_daily_nutrition().kcal < high.average_daily_nutrition().kcal


def test_missing_the_calorie_target_is_reported(conn):
    plan, _ = _plan(conn, days=7, daily_kcal=3500)
    assert any("below your 3500 kcal target" in w and "snack" in w for w in plan.warnings)
    quiet, _ = _plan(conn, days=7)  # no target -> nothing to compare against
    assert not any("kcal" in w for w in quiet.warnings)


@pytest.mark.parametrize(
    "kw", [{"days": 0}, {"days": 15}, {"meals": ()}, {"meals": ("brunch",)}, {"servings": 0}, {"max_repeats": 0}]
)
def test_invalid_requests_are_rejected(conn, kw):
    with pytest.raises(ValueError):
        _plan(conn, **kw)
