"""Password hashing (PBKDF2-SHA256, stdlib) and JWT access tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"


def hash_password(password: str, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def create_access_token(user_id: str, secret: str, expire_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(minutes=expire_minutes)}, secret, ALGORITHM)


def decode_access_token(token: str, secret: str) -> str | None:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])["sub"]
    except jwt.PyJWTError:
        return None


class LoginRateLimiter:
    """In-process limiter: at most `limit` failed logins per key within `window` seconds."""

    def __init__(self, limit: int = 5, window: float = 60.0):
        self.limit, self.window = limit, window
        self._failures: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str) -> deque:
        q = self._failures[key]
        while q and time.monotonic() - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.limit

    def failed(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
