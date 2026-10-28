from datetime import date, timedelta

import pytest

from app.repositories import ingredients as ingredient_repo
from app.repositories import pantry as pantry_repo
from app.repositories import plans as plan_repo
from app.repositories import recipes as recipe_repo
from app.repositories import users as user_repo
from app.schemas import PlanIn
from app.services import Conflict, NotFound, cook_meal, create_plan, saved_plan_grocery, saved_plan_view
from app.seed.catalog import RECIPES

TODAY = date(2026, 10, 25)


def _user(conn, email="a@example.com"):
    return user_repo.create(conn, email, "hash")


def _stock_for_soup(conn, user, lentils=400):
    ings = ingredient_repo.load_all_by_name(conn)
    for name, qty in [("red lentils", lentils), ("onion", 3), ("garlic", 10), ("carrot", 4), ("lemon", 2)]:
        pantry_repo.add_item(conn, user.id, ings[name].id, qty, TODAY + timedelta(days=5))


def test_seed_is_idempotent_and_complete(conn):
    from app.seed.seeder import seed_if_empty

    assert seed_if_empty(conn) is False
    assert len(recipe_repo.load_recipes(conn, None)) == len(RECIPES)
    assert all(r.steps and r.ingredients for r in recipe_repo.load_recipes(conn, None))


def test_custom_recipes_are_private_to_their_owner(conn):
    a, b = _user(conn, "a@example.com"), _user(conn, "b@example.com")
    ing = ingredient_repo.get_by_name(conn, "egg")
    with conn:
        rid = recipe_repo.insert_recipe(
            conn, owner_id=a.id, title="Secret eggs", meal_types=["breakfast"], servings=1,
            ingredients=[(ing.id, 2, "", False)], steps=[{"instruction": "Boil them."}],
        )
    assert recipe_repo.get_recipe(conn, rid, a.id) is not None
    assert recipe_repo.get_recipe(conn, rid, b.id) is None


def test_same_ingredient_twice_is_merged(conn):
    egg = ingredient_repo.get_by_name(conn, "egg")
    with conn:
        rid = recipe_repo.insert_recipe(
            conn, title="Eggs", meal_types=["lunch"], servings=1,
            ingredients=[(egg.id, 2, "", False), (egg.id, 1, "", False)], steps=[{"instruction": "Cook."}],
        )
    assert recipe_repo.get_recipe(conn, rid).ingredients[0].quantity == 3


def test_pantry_summary_aggregates_batches(conn):
    u = _user(conn)
    egg = ingredient_repo.get_by_name(conn, "egg")
    pantry_repo.add_item(conn, u.id, egg.id, 6, TODAY + timedelta(days=9))
    pantry_repo.add_item(conn, u.id, egg.id, 4, TODAY + timedelta(days=2))
    (row,) = pantry_repo.summary(conn, u.id)
    assert row["name"] == "egg" and row["total_quantity"] == 10 and row["batches"] == 2
    assert row["nearest_expiry"] == (TODAY + timedelta(days=2)).isoformat()


def test_expiring_query_and_pantry_isolation(conn):
    a, b = _user(conn, "a@example.com"), _user(conn, "b@example.com")
    milk = ingredient_repo.get_by_name(conn, "milk")
    pantry_repo.add_item(conn, a.id, milk.id, 500, TODAY + timedelta(days=1))
    pantry_repo.add_item(conn, a.id, milk.id, 500, TODAY + timedelta(days=30))
    soon = pantry_repo.expiring(conn, a.id, TODAY, 3)
    assert len(soon) == 1 and soon[0]["days_left"] == 1
    assert pantry_repo.expiring(conn, b.id, TODAY, 3) == []
    assert pantry_repo.delete_item(conn, b.id, soon[0]["id"]) is False  # cannot delete someone else's row


def test_create_plan_saves_meals_and_grocery(conn):
    u = _user(conn)
    _stock_for_soup(conn, u)
    plan, plan_id = create_plan(conn, u, PlanIn(start_date=TODAY, days=2, meals=["lunch", "dinner"]), TODAY)
    assert plan_id and len(plan.meals()) == 4
    view = saved_plan_view(conn, u, plan_id)
    assert len(view["days"]) == 2 and view["days"][0]["meals"][0]["cooked"] is False
    assert isinstance(saved_plan_grocery(conn, u, plan_id), list)
    assert create_plan(conn, u, PlanIn(days=1, save=False), TODAY)[1] is None


def test_cooking_deducts_pantry_first_expiring_first_and_blocks_repeats(conn):
    u = _user(conn)
    _stock_for_soup(conn, u, lentils=250)
    ings = ingredient_repo.load_all_by_name(conn)
    # an extra, sooner-expiring lentil batch that must be used first
    soon_id = pantry_repo.add_item(conn, u.id, ings["red lentils"].id, 100, TODAY + timedelta(days=1))
    _, plan_id = create_plan(conn, u, PlanIn(start_date=TODAY, days=1, meals=["dinner"],
                                             exclude_recipe_ids=[r.id for r in recipe_repo.load_recipes(conn, None) if r.title != "Red Lentil Soup"]), TODAY)
    meal = plan_repo.planned_meals(conn, plan_id)[0]
    result = cook_meal(conn, u, plan_id, meal["id"], TODAY)
    assert result["cooked"] is True
    rows = {r["id"]: r for r in pantry_repo.list_items(conn, u.id) if r["name"] == "red lentils"}
    later_id = next(i for i in rows if i != soon_id)
    # 1 serving of soup needs 200/3 g of lentils; it must come from the batch that expires first
    assert rows[soon_id]["quantity"] == pytest.approx(100 - 200 / 3)
    assert rows[later_id]["quantity"] == 250
    assert plan_repo.get_meal(conn, plan_id, meal["id"])["cooked"] == 1
    with pytest.raises(Conflict):
        cook_meal(conn, u, plan_id, meal["id"], TODAY)  # already cooked


def test_cannot_cook_without_ingredients_and_nothing_changes(conn):
    u = _user(conn)
    _, plan_id = create_plan(conn, u, PlanIn(start_date=TODAY, days=1, meals=["dinner"]), TODAY)  # empty pantry
    meal = plan_repo.planned_meals(conn, plan_id)[0]
    with pytest.raises(Conflict, match="Missing ingredients"):
        cook_meal(conn, u, plan_id, meal["id"], TODAY)
    assert plan_repo.get_meal(conn, plan_id, meal["id"])["cooked"] == 0


def test_plans_belong_to_their_owner(conn):
    a, b = _user(conn, "a@example.com"), _user(conn, "b@example.com")
    _, plan_id = create_plan(conn, a, PlanIn(start_date=TODAY, days=1), TODAY)
    with pytest.raises(NotFound):
        saved_plan_view(conn, b, plan_id)
    with pytest.raises(NotFound):
        cook_meal(conn, b, plan_id, 1, TODAY)


def test_most_cooked_aggregation(conn):
    u = _user(conn)
    _stock_for_soup(conn, u)
    only_soup = [r.id for r in recipe_repo.load_recipes(conn, None) if r.title != "Red Lentil Soup"]
    _, plan_id = create_plan(conn, u, PlanIn(start_date=TODAY, days=1, meals=["dinner"], exclude_recipe_ids=only_soup), TODAY)
    cook_meal(conn, u, plan_id, plan_repo.planned_meals(conn, plan_id)[0]["id"], TODAY)
    (top,) = plan_repo.most_cooked_recipes(conn, u.id)
    assert top["title"] == "Red Lentil Soup" and top["times_cooked"] == 1
