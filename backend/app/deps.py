"""Request dependencies: authentication, project ownership, shared services."""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request
from pymongo.database import Database

from .core.config import Settings, get_settings
from .core.errors import AppError, not_found
from .core.security import decode_access_token
from .db import get_db
from .services.storage import LocalStorage

COOKIE_NAME = "sitescope_session"


def db_dep() -> Database:
    return get_db()


@lru_cache
def _storage(root: str) -> LocalStorage:
    return LocalStorage(root)


def storage_dep(settings: Settings = Depends(get_settings)) -> LocalStorage:
    return _storage(str(settings.storage_dir))


def current_user(request: Request, db: Database = Depends(db_dep), settings: Settings = Depends(get_settings)) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if not token:
        raise AppError(401, "not_authenticated", "Sign in required")
    user_id = decode_access_token(token, settings.jwt_secret)
    user = db.users.find_one({"_id": user_id, "active": True}) if user_id else None
    if user is None:
        raise AppError(401, "invalid_session", "Session expired or invalid — sign in again")
    return user


def owned_filter(user: dict) -> dict:
    """Admins see every project; everyone else sees the projects they created."""
    return {} if user["role"] == "admin" else {"owner_id": user["_id"]}


def load_project(db: Database, project_id: str, user: dict) -> dict:
    project = db.projects.find_one({"_id": project_id} | owned_filter(user))
    if project is None:  # also for other users' projects, so their existence is not revealed
        raise not_found("Project")
    return project
