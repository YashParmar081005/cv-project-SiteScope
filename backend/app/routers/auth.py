from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..core.config import Settings, get_settings
from ..core.errors import AppError
from ..core.security import LoginRateLimiter, create_access_token, hash_password, verify_password
from ..db import new_id, utcnow
from ..deps import COOKIE_NAME, current_user, db_dep
from ..schemas import AuthOut, LoginIn, RegisterIn
from ..serializers import user_out

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = LoginRateLimiter()


def _session(response: Response, user: dict, settings: Settings) -> dict:
    token = create_access_token(user["_id"], settings.jwt_secret, settings.jwt_expire_minutes)
    response.set_cookie(COOKIE_NAME, token, max_age=settings.jwt_expire_minutes * 60, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")
    return {"user": user_out(user), "access_token": token}


def create_user(db: Database, settings: Settings, email: str, name: str, password: str, role: str = "member") -> dict:
    user = {"_id": new_id(), "email": email.lower(), "name": name, "role": role, "active": True,
            "password_hash": hash_password(password, settings.password_iterations), "created_at": utcnow()}
    try:
        db.users.insert_one(user)
    except DuplicateKeyError:
        raise AppError(409, "email_taken", "An account with this email already exists")
    return user


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, response: Response, db: Database = Depends(db_dep),
          settings: Settings = Depends(get_settings)):
    key = f"{body.email.lower()}|{request.client.host if request.client else '-'}"
    if limiter.blocked(key):
        raise AppError(429, "too_many_attempts", "Too many failed sign-in attempts; wait a minute and retry")
    user = db.users.find_one({"email": body.email.lower(), "active": True})
    if user is None or not verify_password(body.password, user["password_hash"]):
        limiter.failed(key)
        raise AppError(401, "invalid_credentials", "Email or password is incorrect")
    limiter.reset(key)
    return _session(response, user, settings)


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, response: Response, db: Database = Depends(db_dep),
             settings: Settings = Depends(get_settings)):
    if not settings.allow_registration:
        raise AppError(403, "registration_disabled", "Self-registration is disabled; ask an administrator")
    return _session(response, create_user(db, settings, body.email, body.name, body.password), settings)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/session")
def session(request: Request, db: Database = Depends(db_dep), settings: Settings = Depends(get_settings)):
    """The signed-in user, or {"user": null} (used by the UI at start-up)."""
    try:
        return {"user": user_out(current_user(request, db, settings))}
    except AppError:
        return {"user": None}
