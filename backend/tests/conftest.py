"""Shared fixtures. API tests run against an in-memory MongoDB (mongomock) and a temporary storage directory;
the real computer-vision pipeline and the trained phase model are used (they are fast and deterministic)."""
from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")

from pathlib import Path

import cv2
import mongomock
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

DEMO_PHOTOS = Path(__file__).resolve().parents[2] / "demo_photos"


def scene(seed: int = 0, w: int = 640, h: int = 480) -> np.ndarray:
    """Synthetic textured image with many corners so ORB has features to match."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 90, np.uint8)
    img += rng.integers(0, 25, (h, w, 3), dtype=np.uint8)
    for _ in range(140):
        x, y = int(rng.integers(0, w - 40)), int(rng.integers(0, h - 40))
        colour = tuple(int(c) for c in rng.integers(0, 255, 3))
        if rng.random() < 0.5:
            cv2.rectangle(img, (x, y), (x + int(rng.integers(8, 40)), y + int(rng.integers(8, 40))), colour, -1)
        else:
            cv2.circle(img, (x + 20, y + 20), int(rng.integers(4, 18)), colour, -1)
    return img


def jpeg(img: np.ndarray, quality: int = 92) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(app_env="test", jwt_secret="t" * 40, password_iterations=1000, storage_dir=tmp_path / "storage",
                    log_json=False, log_level="WARNING", max_upload_mb=2)


@pytest.fixture
def client(settings):
    db = mongomock.MongoClient(tz_aware=True)["sitescope_test"]
    with TestClient(create_app(settings, db)) as c:
        c.db = db
        yield c


def register(client: TestClient, email: str, name: str = "Test User", password: str = "password123") -> dict:
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    client.cookies.clear()  # use explicit bearer headers so several users can act in one test
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def owner(client) -> dict:
    return register(client, "owner@example.com", "Olivia Owner")


PROJECT = {
    "name": "Riverside Residences",
    "construction_type": "residential_building",
    "planned_start_date": "2025-01-01",
    "target_completion_date": "2026-01-01",
    "location": "Ahmedabad, Gujarat",
}


@pytest.fixture
def project(client, owner) -> dict:
    r = client.post("/api/projects", json=PROJECT, headers=owner)
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, project_id, headers, image_bytes, capture_date, filename="site.jpg"):
    return client.post(f"/api/projects/{project_id}/observations", headers=headers, data={"capture_date": capture_date},
                       files={"file": (filename, image_bytes, "image/jpeg")})
