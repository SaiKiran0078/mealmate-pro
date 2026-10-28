"""Regression tests: pantry names must line up with recipes, and search must return relevant recipes."""
import pytest

from app.core import names
from app.core.search import parse_query, search
from app.repositories import ingredients as ingredient_repo
from app.repositories import recipes as recipe_repo


@pytest.mark.parametrize(
    "typed, expected",
    [("Eggs", "egg"), ("Tomatoes", "tomato"), ("potatoes ", "potato"), ("Chicken", "chicken breast"),
     ("chicken breasts", "chicken breast"), ("cheese", "cheddar cheese"), ("Lentils", "red lentils"),
     ("Oat", "oats"), ("Capsicum", "bell pepper"), ("curd", "yogurt"), ("Onions", "onion")],
)
def test_typed_names_resolve_to_catalog_ingredients(conn, typed, expected):
    assert ingredient_repo.resolve(conn, typed).name == expected


@pytest.mark.parametrize("typed", ["coconut milk", "butter beans", "peanuts", "tomato puree"])
def test_different_ingredients_are_not_merged_by_similar_words(conn, typed):
    assert ingredient_repo.resolve(conn, typed) is None


def test_find_or_create_reuses_the_catalog_entry_instead_of_creating_look_alikes(conn):
    before = len(ingredient_repo.load_all(conn))
    for typed in ("Tomatoes", "tomatoes", "chicken", "Eggs"):
        ingredient_repo.find_or_create(conn, typed, "g")
    assert len(ingredient_repo.load_all(conn)) == before
    new = ingredient_repo.find_or_create(conn, "Dragon Fruit", "pieces")
    assert new.name == "dragon fruit" and new.base_unit == "pcs" and not new.nutrition_known


def test_repair_merges_look_alikes_created_by_the_old_lookup(conn):
    from app.repositories import pantry as pantry_repo
    from app.repositories import users as user_repo

    user = user_repo.create(conn, "a@example.com", "x")
    tomato = ingredient_repo.get_by_name(conn, "tomato")
    # what the old code did: "tomatoes" -> "tomatoe" lookup failed -> brand-new nutrition-less ingredient
    with conn:
        conn.execute("INSERT INTO ingredients (name, base_unit, category, nutrition_known) VALUES ('tomatoes','pcs','imported',0)")
    dup = ingredient_repo.get_by_name(conn, "tomatoes")
    pantry_repo.add_item(conn, user.id, dup.id, 4, None)
    assert ingredient_repo.repair_duplicates(conn) == 1
    assert ingredient_repo.get_by_name(conn, "tomatoes") is None
    (row,) = pantry_repo.summary(conn, user.id)
    assert row["name"] == "tomato" and row["total_quantity"] == 4 and row["ingredient_id"] == tomato.id
    assert ingredient_repo.repair_duplicates(conn) == 0  # idempotent


def _recipes(conn):
    return recipe_repo.load_recipes(conn, None)


def titles(outcome):
    return [r.title for r, _ in outcome.hits]


def test_search_finds_dishes_by_ingredient_not_only_by_title(conn):
    assert "Paneer Bhurji" in titles(search(_recipes(conn), "paneer recipes"))
    eggs = titles(search(_recipes(conn), "eggs"))
    assert "Masala Omelette" in eggs and "Egg Fried Rice" in eggs


def test_search_requires_every_term_and_never_returns_unrelated_recipes(conn):
    both = titles(search(_recipes(conn), "recipes containing eggs and spinach"))
    assert both and all(t in both for t in ("Veggie Scramble on Toast", "Spinach & Cheese Breakfast Wrap"))
    out = search(_recipes(conn), "chicken biryani")
    assert out.hits == []                         # no biryani in the catalog: say so
    assert out.related and all("hicken" in r.title for r, _ in out.related)  # partial matches kept separate
    assert search(_recipes(conn), "xyzzy").hits == []


def test_search_is_case_insensitive_and_matches_partial_words(conn):
    assert titles(search(_recipes(conn), "OMELETTE")) == ["Masala Omelette"]
    assert "Home-style Chicken Curry" in titles(search(_recipes(conn), "chick"))


def test_nutrition_and_time_queries_are_parsed_and_enforced(conn):
    q = parse_query("vegetarian meals with 30 grams of protein")
    assert q.diet == "vegetarian" and q.min_protein == 30 and q.terms == []
    assert parse_query("recipes under 500 calories").max_kcal == 500
    assert parse_query("quick meals under 20 minutes").max_minutes == 20
    for r, _ in search(_recipes(conn), "at least 40 grams of protein").hits:
        assert r.nutrition_per_serving.protein >= 40
    for r, _ in search(_recipes(conn), "under 500 calories").hits:
        assert r.nutrition_per_serving.kcal <= 500
    for r, _ in search(_recipes(conn), "quick meals under 20 minutes").hits:
        assert r.total_min <= 20
    for r, _ in search(_recipes(conn), "high protein breakfast").hits:
        assert "breakfast" in r.meal_types and r.nutrition_per_serving.protein >= 25
