"""End-to-end tests through the real HTTP layer (FastAPI TestClient)."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_today
from app.main import create_app

TODAY = date(2026, 10, 26)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "test.db"), jwt_secret="t" * 32))
    app.dependency_overrides[get_today] = lambda: TODAY  # freeze "today" so tests are repeatable
    with TestClient(app) as c:  # entering the context runs startup: creates and seeds the DB
        yield c


def _login(client, email="a@example.com"):
    client.post("/auth/register", json={"email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth(client):
    return _login(client)


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/me", "/pantry", "/recipes", "/plans"])
def test_protected_routes_need_a_token(client, path):
    assert client.get(path).status_code == 401


def test_register_and_login_rules(client):
    body = {"email": "a@example.com", "password": "password123"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409
    assert client.post("/auth/login", json={**body, "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/register", json={"email": "not-an-email", "password": "password123"}).status_code == 422
    assert client.post("/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_pantry_to_suggestion_to_plan_to_cooking(client, auth):
    for name, amount, unit in [("red lentils", 400, "g"), ("onion", 3, "pcs"), ("garlic", 8, "pcs"),
                               ("carrot", 4, "pcs"), ("lemon", 2, "pcs")]:
        assert client.post("/pantry", json={"ingredient": name, "amount": amount, "unit": unit}, headers=auth).status_code == 201

    suggestions = client.get("/recipes/suggestions", headers=auth).json()
    assert suggestions[0]["recipe"]["title"] == "Red Lentil Soup" and suggestions[0]["can_cook_now"] is True

    recipes = client.get("/recipes", headers=auth).json()
    soup_id = next(r["id"] for r in recipes if r["title"] == "Red Lentil Soup")
    others = [r["id"] for r in recipes if r["id"] != soup_id]
    plan = client.post(
        "/plans/generate",
        json={"days": 1, "meals": ["dinner"], "exclude_recipe_ids": others, "start_date": TODAY.isoformat()},
        headers=auth,
    )
    assert plan.status_code == 201
    body = plan.json()
    assert body["days"][0]["meals"][0]["title"] == "Red Lentil Soup" and body["grocery_list"] == []

    saved = client.get(f"/plans/{body['plan_id']}", headers=auth).json()
    meal_id = saved["days"][0]["meals"][0]["meal_id"]
    guide = client.get(f"/recipes/{soup_id}/guide", headers=auth).json()
    assert guide["steps"] and guide["can_cook_now"] is True

    cooked = client.post(f"/plans/{body['plan_id']}/meals/{meal_id}/cook", headers=auth)
    assert cooked.status_code == 200
    assert client.post(f"/plans/{body['plan_id']}/meals/{meal_id}/cook", headers=auth).status_code == 409
    assert client.get("/plans/stats", headers=auth).json()["most_cooked"][0]["title"] == "Red Lentil Soup"


def test_weekly_plan_on_an_empty_pantry_returns_a_shopping_list(client, auth):
    res = client.post("/plans/generate", json={"days": 7, "start_date": TODAY.isoformat()}, headers=auth)
    assert res.status_code == 201
    body = res.json()
    assert len(body["days"]) == 7 and body["grocery_list"]
    assert client.get(f"/plans/{body['plan_id']}/grocery", headers=auth).status_code == 200


@pytest.mark.parametrize(
    "path, payload",
    [("/plans/generate", {"days": 0}), ("/plans/generate", {"meals": ["brunch"]}),
     ("/pantry", {"ingredient": "milk", "amount": 2, "unit": "pcs"}),  # milk has no weight per piece
     ("/pantry", {"ingredient": "milk", "amount": -1})],
)
def test_bad_input_is_a_422_not_a_500(client, auth, path, payload):
    assert client.post(path, json=payload, headers=auth).status_code == 422


def test_users_cannot_see_each_others_data(client, auth):
    client.post("/pantry", json={"ingredient": "egg", "amount": 6}, headers=auth)
    plan_id = client.post("/plans/generate", json={"days": 1}, headers=auth).json()["plan_id"]
    other = _login(client, "b@example.com")
    assert client.get("/pantry", headers=other).json()["items"] == []
    assert client.get(f"/plans/{plan_id}", headers=other).status_code == 404
    assert client.post(f"/plans/{plan_id}/meals/1/cook", headers=other).status_code == 404


def test_custom_recipe_is_private(client, auth):
    body = {"title": "Secret toast", "meal_types": ["snack"], "servings": 1,
            "ingredients": [{"name": "bread", "amount": 2, "unit": "pcs"}], "steps": [{"instruction": "Toast it well."}]}
    created = client.post("/recipes", json=body, headers=auth)
    assert created.status_code == 201
    other = _login(client, "b@example.com")
    assert client.get(f"/recipes/{created.json()['id']}", headers=other).status_code == 404
