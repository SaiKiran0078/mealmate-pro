"""FastAPI dependencies: settings, database connection, current user, today's date."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import Settings
from .core.models import User
from .repositories import users as user_repo
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_today() -> date:
    """Separate dependency so tests can freeze the date."""
    return date.today()


Conn = Annotated[sqlite3.Connection, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
Today = Annotated[date, Depends(get_today)]


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], conn: Conn, settings: Config
) -> User:
    unauthorized = HTTPException(401, "Invalid or missing token", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    user_id = decode_token(creds.credentials, settings.jwt_secret, settings.jwt_algorithm)
    user = user_repo.get(conn, user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]
