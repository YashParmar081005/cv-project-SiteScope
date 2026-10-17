from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from pymongo.database import Database

from ..db import new_id, utcnow
from ..deps import current_user, db_dep, load_project, owned_filter, storage_dep
from ..schemas import ProjectCreate
from ..serializers import clean
from ..services.stages import default_milestones
from ..services.storage import LocalStorage
from ..services.workflow import iso, project_summary

router = APIRouter(prefix="/projects", tags=["projects"])


def planned_milestones(construction_type: str, start, target) -> list[dict]:
    """Template stages for the type, given back-to-back planned windows proportional to their weights."""
    stages, total, cursor, out = default_milestones(construction_type), (target - start).days, start, []
    for i, stage in enumerate(stages):
        end = target if i == len(stages) - 1 else cursor + timedelta(days=round(total * stage["weight"]))
        out.append(stage | {"id": new_id()[:12], "planned_start": iso(cursor), "planned_end": iso(end)})
        cursor = end
    return out


def project_out(db: Database, project: dict) -> dict:
    return clean(project) | {"summary": project_summary(db, project)}


@router.get("")
def list_projects(user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    return [project_out(db, p) for p in db.projects.find(owned_filter(user)).sort("created_at", -1)]


@router.post("", status_code=201)
def create_project(body: ProjectCreate, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    project = {"_id": new_id(), "name": body.name, "construction_type": body.construction_type,
               "location": body.location, "description": body.description,
               "planned_start_date": iso(body.planned_start_date), "target_completion_date": iso(body.target_completion_date),
               "milestones": planned_milestones(body.construction_type, body.planned_start_date, body.target_completion_date),
               "owner_id": user["_id"], "created_at": utcnow()}
    db.projects.insert_one(project)
    return project_out(db, project)


@router.get("/{project_id}")
def get_project(project_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep)):
    return project_out(db, load_project(db, project_id, user))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep),
                   storage: LocalStorage = Depends(storage_dep)):
    load_project(db, project_id, user)
    for collection in ("observations", "image_assets", "analysis_results", "progress_snapshots"):
        db[collection].delete_many({"project_id": project_id})
    db.projects.delete_one({"_id": project_id})
    storage.delete_tree(f"projects/{project_id}")
