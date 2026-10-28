from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..core.units import normalize_unit, to_base
from ..deps import Conn, CurrentUser, Today
from ..repositories import ingredients as ingredient_repo
from ..repositories import pantry as pantry_repo
from ..schemas import PantryIn, PantryPatch

router = APIRouter(prefix="/pantry", tags=["pantry"])


@router.get("")
def pantry_overview(user: CurrentUser, conn: Conn, today: Today) -> dict:
    """Totals per ingredient (SQL aggregation), what expires within 3 days, and what is already past its date."""
    snap = pantry_repo.snapshot(conn, user.id, today)
    return {
        "items": pantry_repo.summary(conn, user.id),
        "expiring_soon": pantry_repo.expiring(conn, user.id, today, 3),
        "expired": snap["expired"],
    }


@router.get("/batches")
def pantry_batches(user: CurrentUser, conn: Conn, today: Today) -> list[dict]:
    """Every batch that still has stock, with its remaining amount (``display``) and expiry status."""
    return pantry_repo.list_items(conn, user.id, today)


@router.post("", status_code=201)
def add_to_pantry(
    body: PantryIn,
    user: CurrentUser,
    conn: Conn,
) -> dict:
    if body.unit:
        normalize_unit(body.unit)  # reject unknown units before anything is created
    known = ingredient_repo.resolve(conn, body.ingredient)
    ing = known or ingredient_repo.find_or_create(conn, body.ingredient, body.unit)

    entered_unit = body.unit or ing.base_unit

    quantity = to_base(
        body.amount,
        entered_unit,
        ing,
    )

    item_id = pantry_repo.add_item(
        conn,
        user.id,
        ing.id,
        quantity,
        body.expires_on,
        entered_amount=body.amount,
        entered_unit=entered_unit,
    )

    typed = body.ingredient.strip().lower()
    return {
        "id": item_id,
        "ingredient": ing.name,
        # tell the UI what happened to the typed name instead of silently creating look-alikes
        "matched_as": ing.name if known and ing.name != typed else None,
        "created_new": known is None,
        "similar": ingredient_repo.suggestions_for(conn, body.ingredient) if known is None else [],
        "nutrition_known": ing.nutrition_known,
        "quantity": round(quantity, 2),
        "unit": ing.base_unit,
        "entered_amount": body.amount,
        "entered_unit": entered_unit,
        "expires_on": (
            body.expires_on.isoformat()
            if body.expires_on
            else None
        ),
    }

@router.patch("/{item_id}")
def edit_pantry_item(item_id: int, body: PantryPatch, user: CurrentUser, conn: Conn, today: Today) -> dict:
    """Correct the remaining amount or expiry date of one batch."""
    quantity = None
    if body.amount is not None:
        row = conn.execute(
            "SELECT ingredient_id FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user.id)).fetchone()
        if row is None:
            raise HTTPException(404, "Pantry item not found")
        ing = ingredient_repo.get(conn, row["ingredient_id"])
        unit = body.unit or ing.base_unit
        quantity = 0.0 if body.amount == 0 else to_base(body.amount, unit, ing)
    if not pantry_repo.update_item(conn, user.id, item_id, quantity=quantity, entered_amount=body.amount,
                                   entered_unit=(body.unit if body.amount is not None else None),
                                   expires_on=body.expires_on, clear_expiry=body.clear_expiry):
        raise HTTPException(404, "Pantry item not found")
    return next((i for i in pantry_repo.list_items(conn, user.id, today) if i["id"] == item_id), {"id": item_id, "quantity": 0})


@router.delete("/{item_id}", status_code=204)
def remove_from_pantry(item_id: int, user: CurrentUser, conn: Conn) -> None:
    if not pantry_repo.delete_item(conn, user.id, item_id):
        raise HTTPException(404, "Pantry item not found")


@router.get("/ingredients/search", tags=["ingredients"])
def search_ingredients(user: CurrentUser, conn: Conn, q: str = Query("", max_length=40)) -> list[dict]:
    return [
        {"id": i.id, "name": i.name, "base_unit": i.base_unit, "category": i.category}
        for i in ingredient_repo.search(conn, q)
    ]
