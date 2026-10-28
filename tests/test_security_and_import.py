import time

from app.integrations import themealdb
from app.repositories import recipes as recipe_repo
from app.security import create_token, decode_token, hash_password, verify_password

SECRET = "x" * 32

MEAL = {
    "idMeal": "52772", "strMeal": "Teriyaki Chicken Casserole", "strCategory": "Chicken", "strArea": "Japanese",
    "strMealThumb": "https://example.com/t.jpg",
    "strInstructions": "Preheat oven to 180C.\r\nMix the soy sauce and chicken in a dish.\r\nBake for 30 minutes until cooked through.",
    "strIngredient1": "soy sauce", "strMeasure1": "3 tbsp",
    "strIngredient2": "Chicken Breasts", "strMeasure2": "2",
    "strIngredient3": "Mirin", "strMeasure3": "1/2 cup",
    "strIngredient4": "Sesame Seed", "strMeasure4": "to taste",
    "strIngredient5": "", "strMeasure5": "",
}


def test_password_hashing():
    h = hash_password("correct horse")
    assert h != "correct horse" and verify_password("correct horse", h)
    assert not verify_password("wrong", h) and not verify_password("x", "garbage")
    assert hash_password("correct horse") != h  # random salt


def test_jwt_roundtrip_expiry_and_tampering():
    token = create_token(42, SECRET, minutes=5)
    assert decode_token(token, SECRET) == 42
    assert decode_token(token, "y" * 32) is None
    assert decode_token(token + "x", SECRET) is None
    expired = create_token(42, SECRET, minutes=-1)
    time.sleep(0.01)
    assert decode_token(expired, SECRET) is None


def test_parse_measure():
    assert themealdb.parse_measure("1 1/2 cups") == (1.5, "cup")
    assert themealdb.parse_measure("200g") == (200.0, "g")
    assert themealdb.parse_measure("2") == (2.0, "pcs")
    assert themealdb.parse_measure("to taste") is None


def test_import_creates_recipe_reuses_known_ingredients_and_flags_nutrition(conn):
    ids = themealdb.import_by_name(conn, "teriyaki", fetch=lambda url: {"meals": [MEAL]})
    recipe = recipe_repo.get_recipe(conn, ids[0])
    assert recipe.source == "themealdb" and recipe.cuisine == "japanese"
    names = {i.ingredient.name for i in recipe.ingredients}
    assert {"soy sauce", "chicken breast", "mirin", "sesame seed"} == names
    assert recipe.nutrition_complete is False  # mirin / sesame are unknown to us
    assert any(s.duration_min == 30 for s in recipe.steps)
    sesame = next(i for i in recipe.ingredients if i.ingredient.name == "sesame seed")
    assert sesame.optional  # "to taste" -> optional


def test_import_is_idempotent(conn):
    first = themealdb.import_by_name(conn, "teriyaki", fetch=lambda url: {"meals": [MEAL]})
    second = themealdb.import_by_name(conn, "teriyaki", fetch=lambda url: {"meals": [MEAL]})
    assert first == second


def test_import_with_no_results(conn):
    assert themealdb.import_by_name(conn, "zzzz", fetch=lambda url: {"meals": None}) == []
