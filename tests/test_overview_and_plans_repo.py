"""Overview numbers and saved-plan helpers, checked at repository level (no HTTP needed)."""
from datetime import date, timedelta

from app.core.planner import PlanRequest, generate_plan
from app.repositories import ingredients as ingredient_repo
from app.repositories import pantry as pantry_repo
from app.repositories import plans as plan_repo
from app.repositories import recipes as recipe_repo
from app.repositories import users as user_repo

TODAY = date(2026, 10, 28)


def _user(conn, email="a@example.com"):
    return user_repo.create(conn, email, "x")


def _save(conn, user, day=TODAY, days=1):
    plan = generate_plan(recipe_repo.load_recipes(conn, user.id), pantry_repo.load_stock(conn, user.id),
                         PlanRequest(start=day, days=days), ingredient_repo.load_all(conn))
    return plan_repo.save_plan(conn, user.id, plan)


def test_snapshot_separates_expiring_from_expired_and_ignores_empty_batches(conn):
    u = _user(conn)
    ing = ingredient_repo.load_all_by_name(conn)
    pantry_repo.add_item(conn, u.id, ing["milk"].id, 500, TODAY + timedelta(days=1))   # expiring
    pantry_repo.add_item(conn, u.id, ing["butter"].id, 200, TODAY - timedelta(days=2)) # already expired
    pantry_repo.add_item(conn, u.id, ing["rice"].id, 1000, None)
    used_up = pantry_repo.add_item(conn, u.id, ing["pasta"].id, 300, None)
    pantry_repo.apply_deductions(conn, [(used_up, 300)])                               # cooked down to 0

    snap = pantry_repo.snapshot(conn, u.id, TODAY)
    assert snap["ingredients"] == 2                       # milk + rice (butter expired, pasta used up)
    assert [i["name"] for i in snap["expiring_soon"]] == ["milk"]
    assert [i["name"] for i in snap["expired"]] == ["butter"]
    assert snap["batches"] == 3                           # the empty pasta batch is not counted
    assert [i["name"] for i in pantry_repo.expiring(conn, u.id, TODAY)] == ["milk"]


def test_pantry_list_shows_remaining_amount_not_the_amount_originally_typed(conn):
    u = _user(conn)
    rice = ingredient_repo.get_by_name(conn, "rice")
    item = pantry_repo.add_item(conn, u.id, rice.id, 1000, None, entered_amount=1, entered_unit="kg")
    pantry_repo.apply_deductions(conn, [(item, 250)])
    (row,) = pantry_repo.list_items(conn, u.id, TODAY)
    assert row["display"] == "750 g" and row["entered_amount"] == 1


def test_saved_plan_survives_a_new_connection_and_can_be_deleted(conn, tmp_path):
    from app.db import connect, init_db

    path = str(tmp_path / "plans.db")
    first = connect(path); init_db(first)
    from app.seed.seeder import seed_if_empty
    seed_if_empty(first)
    u = _user(first)
    plan_id = _save(first, u, days=3)
    first.close()                                          # "server restart"

    again = connect(path)
    assert [p["id"] for p in plan_repo.list_plans(again, u.id)] == [plan_id]
    assert len(plan_repo.planned_meals(again, plan_id)) == 9
    assert plan_repo.delete_plan(again, u.id, plan_id) is True
    assert plan_repo.list_plans(again, u.id) == [] and plan_repo.planned_meals(again, plan_id) == []
    assert plan_repo.delete_plan(again, u.id, plan_id) is False


def test_other_users_cannot_delete_a_plan(conn):
    a, b = _user(conn, "a@example.com"), _user(conn, "b@example.com")
    plan_id = _save(conn, a)
    assert plan_repo.delete_plan(conn, b.id, plan_id) is False
    assert len(plan_repo.list_plans(conn, a.id)) == 1


def test_overlapping_plans_are_not_double_counted_for_a_day(conn):
    u = _user(conn)
    _save(conn, u); _save(conn, u)                         # two plans cover the same day
    meals = plan_repo.meals_on(conn, u.id, TODAY)
    assert [m["meal_type"] for m in meals] == ["breakfast", "lunch", "dinner"]


def test_swap_only_changes_uncooked_meals(conn):
    u = _user(conn)
    plan_id = _save(conn, u)
    meal = plan_repo.planned_meals(conn, plan_id)[0]
    other = next(r for r in recipe_repo.load_recipes(conn, u.id) if r.id != meal["recipe_id"])
    plan_repo.replace_meal(conn, meal["id"], other.id)
    assert plan_repo.get_meal(conn, plan_id, meal["id"])["recipe_id"] == other.id
    plan_repo.mark_cooked(conn, meal["id"])
    plan_repo.replace_meal(conn, meal["id"], meal["recipe_id"])
    assert plan_repo.get_meal(conn, plan_id, meal["id"])["recipe_id"] == other.id   # unchanged
