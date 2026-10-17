from __future__ import annotations

from fastapi import APIRouter, Depends
from pymongo.database import Database

from ..core.errors import AppError, not_found
from ..deps import current_user, db_dep, load_project
from ..schemas import ForecastPreviewIn
from ..serializers import clean
from ..services.progress import planned_curve
from ..services.workflow import (compute_forecast, current_snapshots, milestones_of, parse_date, preview_forecast,
                                 stage_index)

router = APIRouter(prefix="/projects/{project_id}", tags=["estimates"])


@router.get("/progress")
def get_progress(project_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    """Reviewed progress snapshots and the planned curve (for the progress chart)."""
    project = load_project(db, project_id, user)
    curve, basis = planned_curve(milestones_of(project), parse_date(project["planned_start_date"]),
                                 parse_date(project["target_completion_date"]))
    return {"snapshots": [clean(s) for s in current_snapshots(db, project_id)],
            "planned_curve": {"basis": basis, "points": [{"date": d, "progress": v} for d, v in curve] if curve else []}}


@router.get("/forecast")
def get_forecast(project_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    return compute_forecast(db, load_project(db, project_id, user))


@router.post("/forecast/preview")
def forecast_preview(project_id: str, body: ForecastPreviewIn, user: dict = Depends(current_user),
                     db: Database = Depends(db_dep)):
    """What-if forecast for one photo's stage, without saving anything.

    With an unknown within-stage fraction it returns two scenarios — the photo shows the start (0 %) or
    the end (100 %) of that stage — so the answer is an honest range instead of a guessed point.
    """
    project = load_project(db, project_id, user)
    idx = stage_index(project, body.stage_key)
    if idx is None:
        raise AppError(422, "unknown_stage", f"Stage '{body.stage_key}' is not a stage of this project",
                       {"allowed": [m["key"] for m in project["milestones"]]})
    observation = db.observations.find_one({"_id": body.observation_id, "project_id": project_id})
    if observation is None:
        raise not_found("Photo")
    fractions = [body.stage_progress / 100] if body.stage_progress is not None else [0.0, 1.0]
    scenarios = [{"stage_progress": round(f * 100, 1)}
                 | preview_forecast(db, project, observation=observation, stage_idx=idx, fraction=f) for f in fractions]
    return {"stage_key": body.stage_key, "stage_name": project["milestones"][idx]["name"], "scenarios": scenarios}
