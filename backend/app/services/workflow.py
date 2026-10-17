"""Glue between storage, the CV pipeline, progress and forecasting (the DB-aware part of the system)."""
from __future__ import annotations

import logging
from datetime import date, datetime

import cv2
import numpy as np
from pymongo.database import Database

from ..cv import change, pipeline, render
from ..cv.model import METHOD as MODEL_METHOD, PHASE_LABELS, PhaseModel, Sample, reference_samples, vector_of
from ..core.paths import REFERENCE_PHOTOS_DIR
from ..db import new_id, utcnow
from .images import load_rgb
from .prediction import forecast
from .progress import Milestone, Review, compute_snapshots
from .stages import phase_of, stage_from_phase
from .storage import LocalStorage

log = logging.getLogger("app.workflow")


# ------------------------------------------------------------------ helpers
def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def parse_date(s: str | date | None) -> date | None:
    if s is None or isinstance(s, date):
        return s
    return date.fromisoformat(s[:10])


def storable(obj):
    """Convert dates to ISO strings recursively (MongoDB stores datetimes, not dates)."""
    if isinstance(obj, dict):
        return {k: storable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [storable(v) for v in obj]
    if isinstance(obj, date) and not isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def encode_jpeg(img_bgr: np.ndarray, quality: int = 88) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def thumbnail(img_bgr: np.ndarray, max_side: int = 480) -> np.ndarray:
    scale = min(1.0, max_side / max(img_bgr.shape[:2]))
    if scale == 1.0:
        return img_bgr
    return cv2.resize(img_bgr, (round(img_bgr.shape[1] * scale), round(img_bgr.shape[0] * scale)), interpolation=cv2.INTER_AREA)


def load_bgr(storage: LocalStorage, key: str) -> np.ndarray:
    """Decode with EXIF orientation applied, matching the stored width/height and browser display."""
    return cv2.cvtColor(np.asarray(load_rgb(storage.get(key))), cv2.COLOR_RGB2BGR)


def put_asset(db: Database, storage: LocalStorage, *, project_id: str, observation_id: str, kind: str,
              key: str, data: bytes, content_type: str) -> str:
    storage.put(key, data)
    asset_id = new_id()
    db.image_assets.insert_one({"_id": asset_id, "project_id": project_id, "observation_id": observation_id,
                                "kind": kind, "storage_key": key, "content_type": content_type, "created_at": utcnow()})
    return asset_id


def milestones_of(project: dict) -> list[Milestone]:
    return [Milestone(m["id"], m["key"], m["name"], m["weight"], parse_date(m.get("planned_start")),
                      parse_date(m.get("planned_end"))) for m in project["milestones"]]


def stage_index(project: dict, key: str) -> int | None:
    return next((i for i, m in enumerate(project["milestones"]) if m["key"] == key), None)


# ------------------------------------------------------------------ CV analysis
def phase_model_for(db: Database, owner_id: str) -> tuple[PhaseModel | None, int]:
    """Reference profiles + the owner's confirmed photos (the model learns from every confirmation)."""
    samples = reference_samples()
    projects = {p["_id"]: p["construction_type"] for p in db.projects.find({"owner_id": owner_id}, {"construction_type": 1})}
    confirmed = 0
    for o in db.observations.find({"project_id": {"$in": list(projects)}, "stage_review": {"$ne": None},
                                   "analysis_id": {"$ne": None}}, {"analysis_id": 1, "stage_review": 1, "project_id": 1}):
        phase = phase_of(projects[o["project_id"]], o["stage_review"]["stage_key"])
        analysis = db.analysis_results.find_one({"_id": o["analysis_id"]}, {"features": 1})
        if phase and analysis and analysis.get("features"):
            samples.append(Sample(phase, vector_of(analysis["features"]), "confirmed photo", o["_id"]))
            confirmed += 1
    if len({s.phase for s in samples}) < 2:
        return None, confirmed
    return PhaseModel(samples), confirmed


def _neighbour_image(db: Database, storage: LocalStorage, neighbour: dict) -> np.ndarray | None:
    try:
        if neighbour["source"] == "reference":
            return cv2.imread(str(REFERENCE_PHOTOS_DIR / neighbour["ref"]))
        obs = db.observations.find_one({"_id": neighbour["ref"]}, {"thumb_asset_id": 1})
        asset = db.image_assets.find_one({"_id": obs["thumb_asset_id"]}) if obs else None
        return load_bgr(storage, asset["storage_key"]) if asset else None
    except Exception:
        return None


def _classification_step(db: Database, storage: LocalStorage, prediction: dict, stage: dict | None,
                         confirmed: int) -> pipeline.Step:
    tiles = []
    for n in prediction["neighbours"]:
        img = _neighbour_image(db, storage, n)
        if img is not None:
            label = f"{PHASE_LABELS[n['phase']].split(' ')[0]} d={n['distance']:.2f}" + (" (yours)" if n["source"] != "reference" else "")
            tiles.append((label, render.crop_to(img, 240, 180)))
    votes = sorted(prediction["votes"].items(), key=lambda kv: -kv[1])
    image = render.bar_chart([(PHASE_LABELS[p], v) for p, v in votes], 640, highlight=PHASE_LABELS[prediction["phase"]], fmt="{:.0%}")
    if tiles:
        image = np.vstack([image, render.grid(tiles, cols=len(tiles), tile_width=640 // len(tiles))])
    return pipeline.Step(
        "classification", "Phase classification (k-nearest neighbours, k = 5)",
        "Standardise features (z-scores) → RMS distance to every training photo → 5 nearest vote, weighted by 1 / distance",
        "The feature vector is compared with the feature vectors of labelled reference site photos and your confirmed "
        "photos. The 5 most similar photos (shown below) vote for their construction phase.",
        {"k": 5, "training_photos": sum(prediction["references"].values()),
         "of_which_your_confirmed_photos": confirmed, "photos_per_phase": prediction["references"]},
        {"phase": prediction["phase_label"], "confidence": prediction["confidence"],
         "vote_share": {PHASE_LABELS[p]: v for p, v in votes},
         "nearest_photos": [f"{PHASE_LABELS[n['phase']]} ({n['distance']:.2f})" for n in prediction["neighbours"]],
         "position_in_phase": prediction["position"],
         "suggested_stage": f"{stage['stage_name']} · {stage['stage_progress']} %" if stage else None},
        image)


def run_analysis(db: Database, storage: LocalStorage, project: dict, obs: dict) -> dict:
    """Run the CV pipeline on a photo, classify its phase, compare with the previous photo, store every step."""
    try:
        image = load_bgr(storage, obs["original"]["storage_key"])
        result = pipeline.analyze(image)
    except Exception as exc:  # failures are shown, never replaced by made-up output
        log.exception("analysis failed for photo %s", obs["_id"])
        db.observations.update_one({"_id": obs["_id"]}, {"$set": {"status": "analysis_failed",
                                                                  "analysis_error": f"Analysis failed: {exc.__class__.__name__}"}})
        return db.observations.find_one({"_id": obs["_id"]})

    steps = list(result.steps)
    model, confirmed = phase_model_for(db, project["owner_id"])
    prediction, suggestion, note = None, None, None
    if model is None:
        note = "No trained phase profiles yet: run `python -m app.cv.train` (or confirm photos of two different phases)."
    else:
        prediction = model.predict(vector_of(result.features))
        stage = stage_from_phase(project, prediction["phase"], prediction["position"])
        prediction["stage"] = stage
        steps.append(_classification_step(db, storage, prediction, stage, confirmed))
        if stage:
            suggestion = {"stage_key": stage["stage_key"], "stage_index": stage["stage_index"],
                          "stage_progress": stage["stage_progress"], "phase": prediction["phase"],
                          "phase_label": prediction["phase_label"], "confidence": prediction["confidence"]}

    previous = next(iter(db.observations.find({"project_id": project["_id"], "_id": {"$ne": obs["_id"]},
                                               "capture_date": {"$lte": obs["capture_date"]}})
                         .sort([("capture_date", -1), ("uploaded_at", -1)]).limit(1)), None)
    change_metrics = None
    if previous:
        try:
            prev_img = pipeline.working_image(load_bgr(storage, previous["original"]["storage_key"]))
            days = (parse_date(obs["capture_date"]) - parse_date(previous["capture_date"])).days
            step = change.compare(prev_img, result.image, days)
            step.metrics["previous_photo_date"] = previous["capture_date"]
            steps.append(step)
            change_metrics = step.metrics
        except Exception:
            log.exception("change detection failed")

    analysis_id = new_id()
    stored_steps = []
    for n, step in enumerate(steps, 1):
        asset_id = None
        if step.image is not None:
            asset_id = put_asset(db, storage, project_id=project["_id"], observation_id=obs["_id"], kind="step",
                                 key=f"projects/{project['_id']}/observations/{obs['_id']}/steps/{n:02d}_{step.key}.jpeg",  # not .jpg: see routers/observations.py
                                 data=encode_jpeg(step.image, 85), content_type="image/jpeg")
        stored_steps.append({"number": n, "key": step.key, "title": step.title, "algorithm": step.algorithm,
                             "purpose": step.purpose, "params": step.params, "metrics": step.metrics, "asset_id": asset_id})
    db.analysis_results.insert_one({
        "_id": analysis_id, "observation_id": obs["_id"], "project_id": project["_id"], "method": pipeline.METHOD,
        "model_method": MODEL_METHOD, "steps": stored_steps, "features": result.features, "prediction": prediction,
        "change": change_metrics, "note": note, "created_at": utcnow()})
    db.observations.update_one({"_id": obs["_id"]}, {"$set": {
        "status": "analyzed", "analysis_error": None, "analysis_id": analysis_id, "stage_suggestion": suggestion,
        "summary": {"phase": prediction and prediction["phase_label"], "confidence": prediction and prediction["confidence"],
                    "changed_area_share": change_metrics and change_metrics.get("changed_area_share")}}})
    return db.observations.find_one({"_id": obs["_id"]})


# ------------------------------------------------------------------ progress
def stored_reviews(db: Database, project: dict, exclude_id: str | None = None) -> list[Review]:
    """Confirmed photos as progress inputs (a stage that no longer exists is ignored)."""
    reviews = []
    for o in db.observations.find({"project_id": project["_id"], "stage_review": {"$ne": None}}):
        idx = stage_index(project, o["stage_review"]["stage_key"])
        if o["_id"] == exclude_id or idx is None:
            continue
        fraction = o["stage_review"].get("stage_progress")
        reviews.append(Review(o["_id"], parse_date(o["capture_date"]), idx, None if fraction is None else fraction / 100))
    return reviews


def recompute_progress(db: Database, project: dict) -> list[dict]:
    """Replace the project's progress snapshots with ones computed from all current reviews."""
    snapshots = [storable(s) | {"_id": new_id(), "project_id": project["_id"], "computed_at": utcnow()}
                 for s in compute_snapshots(milestones_of(project), stored_reviews(db, project))]
    db.progress_snapshots.delete_many({"project_id": project["_id"]})
    if snapshots:
        db.progress_snapshots.insert_many(snapshots)
    return snapshots


def current_snapshots(db: Database, project_id: str) -> list[dict]:
    return list(db.progress_snapshots.find({"project_id": project_id}).sort("as_of_date", 1))


def _latest_capture(db: Database, project_id: str) -> date | None:
    latest = next(iter(db.observations.find({"project_id": project_id}).sort("capture_date", -1).limit(1)), None)
    return parse_date(latest["capture_date"]) if latest else None


def _forecast(db: Database, project: dict, snapshots: list[dict], extra_capture: date | None = None) -> dict:
    latest = max((d for d in (_latest_capture(db, project["_id"]), extra_capture) if d), default=None)
    return storable(forecast(planned_start=parse_date(project["planned_start_date"]),
                             target=parse_date(project["target_completion_date"]), milestones=milestones_of(project),
                             snapshots=[{"as_of_date": parse_date(s["as_of_date"]), "progress": s["progress"],
                                         "lower_bound": s.get("lower_bound", False)} for s in snapshots],
                             today=date.today(), latest_observation_date=latest))


def compute_forecast(db: Database, project: dict) -> dict:
    return _forecast(db, project, current_snapshots(db, project["_id"]))


def preview_forecast(db: Database, project: dict, *, observation: dict, stage_idx: int, fraction: float | None) -> dict:
    """What-if: forecast as if this photo were confirmed with this stage. Nothing is stored."""
    reviews = stored_reviews(db, project, exclude_id=observation["_id"])
    reviews.append(Review(observation["_id"], parse_date(observation["capture_date"]), stage_idx, fraction))
    snaps = compute_snapshots(milestones_of(project), reviews)
    return {"forecast": _forecast(db, project, snaps, parse_date(observation["capture_date"])),
            "progress": snaps[-1]["progress"] if snaps else None, "snapshot": storable(snaps[-1]) if snaps else None}


def project_summary(db: Database, project: dict) -> dict:
    snaps = current_snapshots(db, project["_id"])
    fc = compute_forecast(db, project)
    return {
        "photos": db.observations.count_documents({"project_id": project["_id"]}),
        "progress": snaps[-1]["progress"] if snaps else None,
        "progress_date": snaps[-1]["as_of_date"] if snaps else None,
        "forecast": {k: fc[k] for k in ("status", "estimated_completion_date", "range", "confidence", "predicted_delay_days")},
    }
