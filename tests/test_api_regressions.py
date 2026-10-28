"""HTTP-level regression tests for: overview numbers, plan persistence, pantry -> recipes, recipe search."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_today
from app.main import create_app

TODAY = date(2026, 10, 28)
SETTINGS = dict(jwt_secret="t" * 32)


def _client(db_path):
    app = create_app(Settings(db_path=str(db_path), **SETTINGS))
    app.dependency_overrides[get_today] = lambda: TODAY
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    with _client(tmp_path / "t.db") as c:
        yield c


def _auth(client, email="a@example.com"):
    client.post("/auth/register", json={"email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _add(client, auth, name, amount, unit=None, expires=None):
    body = {"ingredient": name, "amount": amount}
    if unit:
        body["unit"] = unit
    if expires:
        body["expires_on"] = expires.isoformat()
    res = client.post("/pantry", json=body, headers=auth)
    assert res.status_code == 201, res.text
    return res.json()


def test_plural_and_generic_names_match_catalog_ingredients(client):
    auth = _auth(client)
    assert _add(client, auth, "Tomatoes", 4, "pcs")["matched_as"] == "tomato"
    chicken = _add(client, auth, "chicken", 500, "g")
    assert chicken["ingredient"] == "chicken breast" and chicken["created_new"] is False
    new = _add(client, auth, "dragon fruit", 2, "pcs")
    assert new["created_new"] is True
    names = {i["name"] for i in client.get("/pantry/batches", headers=auth).json()}
    assert {"tomato", "chicken breast", "dragon fruit"} <= names and "tomatoes" not in names


def test_pantry_with_typed_plurals_produces_recipe_suggestions(client):
    auth = _auth(client)
    for name, amount, unit in [("Eggs", 6, "pcs"), ("Tomatoes", 3, "pcs"), ("Onions", 2, "pcs"), ("Spinach", 100, "g")]:
        _add(client, auth, name, amount, unit)
    picks = client.get("/recipes/suggestions?min_coverage=0.3", headers=auth).json()
    assert picks and all(p["coverage_pct"] >= 30 for p in picks)
    assert any(p["status"] == "ready" for p in picks)


def test_overview_numbers_come_from_one_consistent_source(client):
    auth = _auth(client)
    _add(client, auth, "milk", 500, "ml", TODAY + timedelta(days=1))
    _add(client, auth, "butter", 200, "g", TODAY - timedelta(days=3))
    _add(client, auth, "rice", 1, "kg")
    _add(client, auth, "rice", 500, "g")
    d = client.get("/dashboard", headers=auth).json()
    assert d["pantry"]["ingredients"] == 2 and d["pantry"]["batches"] == 4
    assert [i["name"] for i in d["pantry"]["expiring_soon"]] == ["milk"]
    assert [i["name"] for i in d["pantry"]["expired"]] == ["butter"]
    batches = client.get("/pantry/batches", headers=auth).json()
    assert len({b["name"] for b in batches if b["status"] != "expired"}) == d["pantry"]["ingredients"]
    assert d["recipes"]["ready_to_cook"] >= 0 and d["plans"]["count"] == 0
    assert d["nutrition_today"]["planned"] is None


def test_empty_pantry_has_no_ready_recipes_and_no_picks(client):
    d = client.get("/dashboard", headers=_auth(client)).json()
    assert d["recipes"]["ready_to_cook"] == 0 and d["recipes"]["picks"] == []


def test_saved_plan_persists_across_a_server_restart_and_can_be_deleted(tmp_path):
    db = tmp_path / "restart.db"
    with _client(db) as first:
        auth = _auth(first)
        body = first.post("/plans/generate", json={"days": 7, "start_date": TODAY.isoformat()}, headers=auth).json()
        assert body["saved"] is True and body["plan_id"]
        plan_id = body["plan_id"]
    with _client(db) as second:  # brand-new app instance, same database file
        token = second.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        listed = second.get("/plans", headers=auth).json()
        assert [p["id"] for p in listed] == [plan_id] and listed[0]["meals"] == 21
        saved = second.get(f"/plans/{plan_id}", headers=auth).json()
        assert len(saved["days"]) == 7 and saved["days"][0]["meals"][0]["title"]
        assert second.delete(f"/plans/{plan_id}", headers=auth).status_code == 204
        assert second.get(f"/plans/{plan_id}", headers=auth).status_code == 404


def test_unsaved_plan_is_reported_as_not_saved(client):
    auth = _auth(client)
    body = client.post("/plans/generate", json={"days": 1, "save": False}, headers=auth).json()
    assert body["saved"] is False and body["plan_id"] is None
    assert client.get("/plans", headers=auth).json() == []


def test_swap_a_planned_meal_and_it_persists(client):
    auth = _auth(client)
    plan = client.post("/plans/generate", json={"days": 1, "start_date": TODAY.isoformat()}, headers=auth).json()
    saved = client.get(f"/plans/{plan['plan_id']}", headers=auth).json()
    meal = saved["days"][0]["meals"][0]
    options = client.get(f"/recipes?meal_type={meal['meal_type']}", headers=auth).json()
    other = next(r for r in options if r["id"] != meal["recipe_id"])
    res = client.put(f"/plans/{plan['plan_id']}/meals/{meal['meal_id']}", json={"recipe_id": other["id"]}, headers=auth)
    assert res.status_code == 200
    again = client.get(f"/plans/{plan['plan_id']}", headers=auth).json()
    assert again["days"][0]["meals"][0]["recipe_id"] == other["id"]


def test_recipe_search_endpoint_is_relevant_and_pantry_aware(client):
    auth = _auth(client)
    _add(client, auth, "paneer", 300, "g")
    _add(client, auth, "onion", 2, "pcs")
    _add(client, auth, "tomato", 3, "pcs")
    res = client.get("/recipes/search", params={"q": "paneer"}, headers=auth).json()
    assert [r["recipe"]["title"] for r in res["results"]] == ["Paneer Bhurji"]
    assert res["results"][0]["coverage_pct"] > 0
    miss = client.get("/recipes/search", params={"q": "chicken biryani"}, headers=auth).json()
    assert miss["total"] == 0 and miss["results"] == [] and miss["suggestions"]
    protein = client.get("/recipes/search", params={"q": "at least 40 grams of protein", "sort": "protein"}, headers=auth).json()
    assert protein["results"] and all(r["recipe"]["nutrition_per_serving"]["protein_g"] >= 40 for r in protein["results"])
    proteins = [r["recipe"]["nutrition_per_serving"]["protein_g"] for r in protein["results"]]
    assert proteins == sorted(proteins, reverse=True)
    paged = client.get("/recipes/search", params={"limit": 3, "offset": 3}, headers=auth).json()
    assert len(paged["results"]) == 3 and paged["total"] >= 19


def test_edit_pantry_amount_and_unknown_unit_is_rejected_without_creating_ingredients(client):
    auth = _auth(client)
    item = _add(client, auth, "rice", 1, "kg")
    assert client.patch(f"/pantry/{item['id']}", json={"amount": 250, "unit": "g"}, headers=auth).json()["display"] == "250 g"
    assert client.patch(f"/pantry/{item['id']}", json={"amount": 0}, headers=auth).json()["quantity"] == 0
    assert client.get("/pantry/batches", headers=auth).json() == []
    before = len(client.get("/pantry/ingredients/search?q=", headers=auth).json())
    assert client.post("/pantry", json={"ingredient": "mystery", "amount": 1, "unit": "bushel"}, headers=auth).status_code == 422
    assert len(client.get("/pantry/ingredients/search?q=", headers=auth).json()) == before
