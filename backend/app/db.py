"""MongoDB access (PyMongo). Image binaries never go into MongoDB — only metadata and results."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

_client: MongoClient | None = None
_db: Database | None = None


def connect(uri: str, name: str) -> Database:
    global _client, _db
    _client = MongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    _db = _client[name]
    return _db


def set_database(db: Database) -> None:
    """Inject a database (used by tests with mongomock)."""
    global _db
    _db = db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("database not initialised")
    return _db


def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client, _db = None, None


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_indexes(db: Database) -> None:
    db.users.create_index("email", unique=True)
    db.projects.create_index([("owner_id", ASCENDING), ("created_at", DESCENDING)])
    db.observations.create_index([("project_id", ASCENDING), ("capture_date", ASCENDING)])
    db.observations.create_index([("project_id", ASCENDING), ("original.sha256", ASCENDING)], unique=True)
    db.image_assets.create_index("project_id")
    db.analysis_results.create_index("observation_id")
    db.progress_snapshots.create_index([("project_id", ASCENDING), ("as_of_date", ASCENDING)])
