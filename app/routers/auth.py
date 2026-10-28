from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException

from ..deps import Config, Conn, CurrentUser
from ..repositories import users as user_repo
from ..schemas import Credentials, ProfileIn
from ..security import create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


def _user_dict(u) -> dict:
    return {"id": u.id, "email": u.email, "daily_kcal": u.daily_kcal, "diet": u.diet, "household_size": u.household_size}


@router.post("/auth/register", status_code=201)
def register(body: Credentials, conn: Conn) -> dict:
    try:
        user = user_repo.create(conn, body.email, hash_password(body.password))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That email is already registered") from None
    return _user_dict(user)


@router.post("/auth/login")
def login(body: Credentials, conn: Conn, settings: Config) -> dict:
    found = user_repo.get_with_hash(conn, body.email)
    # Same message for "no such user" and "wrong password": do not leak which emails exist.
    if not found or not verify_password(body.password, found[1]):
        raise HTTPException(401, "Incorrect email or password")
    token = create_token(found[0].id, settings.jwt_secret, settings.token_minutes, settings.jwt_algorithm)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return _user_dict(user)


@router.put("/me")
def update_me(body: ProfileIn, user: CurrentUser, conn: Conn) -> dict:
    return _user_dict(user_repo.update_profile(conn, user.id, body.daily_kcal, body.diet, body.household_size))
