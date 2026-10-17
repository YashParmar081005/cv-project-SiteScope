from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pymongo.database import Database

from ..deps import current_user, db_dep, load_project, storage_dep
from ..services.reports import build_pdf
from ..services.storage import LocalStorage
from ..services.workflow import compute_forecast, project_summary
from .insights import get_progress

router = APIRouter(prefix="/projects/{project_id}", tags=["reports"])


@router.get("/report.pdf")
def report_pdf(project_id: str, user: dict = Depends(current_user), db: Database = Depends(db_dep),
               storage: LocalStorage = Depends(storage_dep)):
    project = load_project(db, project_id, user)
    observations = list(db.observations.find({"project_id": project_id}).sort([("capture_date", -1), ("uploaded_at", -1)]).limit(4))
    pdf = build_pdf(project=project, summary=project_summary(db, project), progress=get_progress(project_id, user, db),
                    forecast=compute_forecast(db, project), observations=observations, storage=storage,
                    generated_by=user["name"])
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", project["name"])[:60] + "_report.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
