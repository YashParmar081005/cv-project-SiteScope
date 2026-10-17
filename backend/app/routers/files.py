from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pymongo.database import Database

from ..core.errors import not_found
from ..deps import current_user, db_dep, load_project, storage_dep
from ..services.storage import LocalStorage

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{asset_id}")
def get_file(asset_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep),
             storage: LocalStorage = Depends(storage_dep)):
    asset = db.image_assets.find_one({"_id": asset_id})
    if asset is None:
        raise not_found("File")
    load_project(db, asset["project_id"], user)  # project-level authorisation
    path = storage.path(asset["storage_key"])
    if not path.exists():
        raise not_found("File content")
    return FileResponse(path, media_type=asset["content_type"],
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
