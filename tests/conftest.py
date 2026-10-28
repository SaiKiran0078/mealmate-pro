import pytest

from app.db import connect, init_db
from app.repositories import ingredients as ingredient_repo
from app.repositories import recipes as recipe_repo
from app.seed.seeder import seed_if_empty


@pytest.fixture
def conn():
    """A fresh in-memory database, already seeded with the built-in catalog."""
    c = connect(":memory:")
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()


@pytest.fixture
def catalog(conn):
    """(recipes_by_title, ingredients_by_name) loaded from the seeded database."""
    recipes = {r.title: r for r in recipe_repo.load_recipes(conn, None)}
    return recipes, ingredient_repo.load_all_by_name(conn)
