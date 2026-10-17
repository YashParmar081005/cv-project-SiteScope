from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..core.config import Settings, get_settings
from ..core.errors import AppError, not_found
from ..db import new_id, utcnow
from ..deps import current_user, db_dep, load_project, storage_dep
from ..schemas import ReviewIn
from ..serializers import analysis_out, observation_out
from ..services.explain import explain
from ..services.images import InvalidImage, inspect_image, sha256_bytes
from ..services.reports import build_analysis_pdf
from ..services.storage import LocalStorage
from ..services.workflow import (encode_jpeg, load_bgr, preview_forecast, put_asset, recompute_progress, run_analysis,
                                 stage_index, thumbnail)

router = APIRouter(tags=["observations"])
# Stored JPEGs use ".jpeg", never ".jpg": anti-ransomware tools such as 360 Total Security kill a process that
# deletes more than a few ".jpg" files, which would take the server down when a project or photo is deleted.
JPEG = ".jpeg"
EXTENSIONS = {"image/jpeg": JPEG, "image/png": ".png", "image/webp": ".webp", "image/bmp": ".bmp"}
EARLIEST_CAPTURE = date(1990, 1, 1)


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks, size = [], 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise AppError(413, "file_too_large", f"File exceeds the {limit // (1024 * 1024)} MB limit")
        chunks.append(chunk)
    if size == 0:
        raise AppError(422, "empty_file", "The uploaded file is empty")
    return b"".join(chunks)


def used_result(project: dict, obs: dict) -> dict | None:
    """The stage behind this photo's result: the user's confirmation, otherwise the CV suggestion."""
    source = obs.get("stage_review") or obs.get("stage_suggestion")
    idx = stage_index(project, source["stage_key"]) if source else None
    if idx is None:
        return None
    return {"source": "confirmed" if obs.get("stage_review") else "cv_suggestion", "stage_key": source["stage_key"],
            "stage_index": idx, "stage_name": project["milestones"][idx]["name"], "stage_progress": source.get("stage_progress")}


def observation_detail(db: Database, obs: dict, project: dict) -> dict:
    analysis = db.analysis_results.find_one({"_id": obs["analysis_id"]}) if obs.get("analysis_id") else None
    used = used_result(project, obs)
    preview = None
    if used:
        fraction = None if used["stage_progress"] is None else used["stage_progress"] / 100
        preview = preview_forecast(db, project, observation=obs, stage_idx=used["stage_index"], fraction=fraction)
    return observation_out(obs) | {
        "analysis": analysis_out(analysis),
        "result": used and {"used": used, "progress": preview["progress"], "forecast": preview["forecast"]},
        "explanation": explain(project, analysis, used, preview),
        "project": {k: project[k] for k in ("name", "construction_type", "milestones", "planned_start_date",
                                            "target_completion_date")} | {"id": project["_id"]},
    }


@router.post("/projects/{project_id}/observations", status_code=201)
async def upload_observation(project_id: str, file: UploadFile = File(...), capture_date: date = Form(...),
                             user: dict = Depends(current_user), db: Database = Depends(db_dep),
                             storage: LocalStorage = Depends(storage_dep), settings: Settings = Depends(get_settings)):
    project = load_project(db, project_id, user)
    if capture_date > date.today():
        raise AppError(422, "validation_error", "capture_date cannot be in the future")
    if capture_date < EARLIEST_CAPTURE:
        raise AppError(422, "validation_error", f"capture_date must be on or after {EARLIEST_CAPTURE}")
    data = await _read_limited(file, settings.max_upload_bytes)
    # decoding, storage and the CV pipeline are CPU/IO bound: keep them off the event loop
    return await run_in_threadpool(_create_observation, project, data, file.filename, capture_date, db, storage)


def _create_observation(project: dict, data: bytes, filename: str | None, capture_date: date, db: Database,
                        storage: LocalStorage) -> dict:
    project_id = project["_id"]
    try:
        info = inspect_image(data)
    except InvalidImage as exc:
        raise AppError(415, "invalid_image", f"Not a valid image: {exc}")
    sha = sha256_bytes(data)
    existing = db.observations.find_one({"project_id": project_id, "original.sha256": sha})
    if existing:
        raise AppError(409, "duplicate_image", "This exact photo was already uploaded to the project",
                       {"observation_id": existing["_id"]})

    obs_id = new_id()
    prefix = f"projects/{project_id}/observations/{obs_id}"
    key = f"{prefix}/original{EXTENSIONS[info.content_type]}"
    original_id = put_asset(db, storage, project_id=project_id, observation_id=obs_id, kind="original", key=key,
                            data=data, content_type=info.content_type)
    thumb_id = put_asset(db, storage, project_id=project_id, observation_id=obs_id, kind="thumbnail",
                         key=f"{prefix}/thumb{JPEG}", data=encode_jpeg(thumbnail(load_bgr(storage, key)), 80),
                         content_type="image/jpeg")
    obs = {
        "_id": obs_id, "project_id": project_id, "capture_date": capture_date.isoformat(), "uploaded_at": utcnow(),
        "original": {"asset_id": original_id, "storage_key": key, "width": info.width, "height": info.height,
                     "sha256": sha, "filename": re.sub(r"[^\w.\- ]+", "_", filename or "upload")[:120]},
        "thumb_asset_id": thumb_id, "status": "uploaded", "analysis_error": None, "analysis_id": None,
        "summary": None, "stage_suggestion": None, "stage_review": None,
    }
    try:
        db.observations.insert_one(obs)
    except DuplicateKeyError:  # concurrent upload of the same bytes
        raise AppError(409, "duplicate_image", "This exact photo was already uploaded to the project")
    return observation_detail(db, run_analysis(db, storage, project, obs), project)


@router.get("/projects/{project_id}/observations")
def list_observations(project_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    load_project(db, project_id, user)
    docs = db.observations.find({"project_id": project_id}).sort([("capture_date", -1), ("uploaded_at", -1)])
    return [observation_out(o) for o in docs]


def _load_observation(db: Database, observation_id: str, user: dict) -> tuple[dict, dict]:
    obs = db.observations.find_one({"_id": observation_id})
    if obs is None:
        raise not_found("Photo")
    return obs, load_project(db, obs["project_id"], user)


@router.get("/observations/{observation_id}")
def get_observation(observation_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    obs, project = _load_observation(db, observation_id, user)
    return observation_detail(db, obs, project)


@router.get("/observations/{observation_id}/report.pdf")
def observation_report(observation_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep),
                       storage: LocalStorage = Depends(storage_dep)):
    obs, project = _load_observation(db, observation_id, user)
    detail = observation_detail(db, obs, project)
    keys = {a["_id"]: a["storage_key"] for a in db.image_assets.find({"observation_id": observation_id})}
    pdf = build_analysis_pdf(project=project, obs=obs, detail=detail, asset_keys=keys, storage=storage, generated_by=user["name"])
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{project['name']}_photo_{obs['capture_date']}")[:80] + "_analysis.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.put("/observations/{observation_id}/review")
def review_stage(observation_id: str, body: ReviewIn, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    obs, project = _load_observation(db, observation_id, user)
    if stage_index(project, body.stage_key) is None:
        raise AppError(422, "unknown_stage", f"Stage '{body.stage_key}' is not a stage of this project",
                       {"allowed": [m["key"] for m in project["milestones"]]})
    review = {"stage_key": body.stage_key, "stage_progress": body.stage_progress, "reviewer_id": user["_id"],
              "reviewer_name": user["name"], "reviewed_at": utcnow(),
              "agrees_with_suggestion": (obs.get("stage_suggestion") or {}).get("stage_key") == body.stage_key}
    db.observations.update_one({"_id": observation_id}, {"$set": {"stage_review": review}})
    recompute_progress(db, project)
    return observation_detail(db, db.observations.find_one({"_id": observation_id}), project)


@router.delete("/observations/{observation_id}", status_code=204)
def delete_observation(observation_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep),
                       storage: LocalStorage = Depends(storage_dep)):
    obs, project = _load_observation(db, observation_id, user)
    for collection in ("image_assets", "analysis_results"):
        db[collection].delete_many({"observation_id": observation_id})
    db.observations.delete_one({"_id": observation_id})
    storage.delete_tree(f"projects/{project['_id']}/observations/{observation_id}")
    recompute_progress(db, project)
