"""FastAPI application factory. Serves the API under /api and the static frontend at /.

    uvicorn app.main:app --port 8000            # from backend/
"""
from __future__ import annotations

import logging
import mimetypes
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pymongo.database import Database

from . import __version__, db as database
from .core.config import Settings, get_settings
from .core.errors import install_error_handlers
from .core.logging import configure_logging, request_id_var
from .routers import auth, files, health, insights, observations, projects, reports

log = logging.getLogger("app")

# Windows has no registry entry for these, so StaticFiles would serve them as octet-stream.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")

# Scripts only from this origin; images from this origin (plus inline SVG/data icons).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def bootstrap_admin(db: Database, settings: Settings) -> None:
    if settings.admin_email and settings.admin_password and db.users.count_documents({"role": "admin"}) == 0:
        if db.users.find_one({"email": settings.admin_email.lower()}):
            db.users.update_one({"email": settings.admin_email.lower()}, {"$set": {"role": "admin"}})
        else:
            auth.create_user(db, settings, settings.admin_email, settings.admin_name, settings.admin_password, role="admin")
        log.info("bootstrap admin ensured: %s", settings.admin_email)


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        connected = db is None
        active = db if db is not None else database.connect(settings.mongo_uri, settings.mongo_db)
        database.set_database(active)
        if connected:
            active.command("ping")
        database.ensure_indexes(active)
        bootstrap_admin(active, settings)
        log.info("startup complete (env=%s, db=%s)", settings.app_env, settings.mongo_db)
        yield
        if connected:
            database.close()

    app = FastAPI(title="SiteScope API", version=__version__, lifespan=lifespan,
                  description="Construction completion-time estimation from site photos.")
    app.dependency_overrides[get_settings] = lambda: settings

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "same-origin"
            if not request.url.path.startswith(("/docs", "/redoc")):  # Swagger UI loads from its own CDN
                response.headers["Content-Security-Policy"] = CSP
            log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                                       "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
            return response
        finally:
            request_id_var.reset(token)

    install_error_handlers(app)
    for router in (health.router, auth.router, projects.router, observations.router, insights.router,
                   reports.router, files.router):
        app.include_router(router, prefix="/api")
    if settings.frontend_dir and (settings.frontend_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()
