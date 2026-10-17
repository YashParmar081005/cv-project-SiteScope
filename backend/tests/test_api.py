"""API integration tests: the full user journey plus privacy, validation and failure handling."""
from datetime import date

import cv2
import numpy as np

from app.cv import model as phase_model
from app.services import workflow

from .conftest import DEMO_PHOTOS, PROJECT, jpeg, register, scene, upload

H_SHIFT = np.array([[0.99, -0.03, 15.0], [0.03, 0.99, -8.0], [0.0, 0.0, 1.0]])


def demo(name: str) -> bytes:
    return (DEMO_PHOTOS / name).read_bytes()


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_auth_flow_and_errors(client):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/auth/session").json() == {"user": None}
    headers = register(client, "a@example.com", "Ann")
    assert client.get("/api/auth/session", headers=headers).json()["user"]["email"] == "a@example.com"
    r = client.post("/api/auth/register", json={"email": "a@example.com", "name": "Ann", "password": "password123"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    r = client.post("/api/auth/register", json={"email": "bad", "name": "X", "password": "short"})
    assert r.status_code == 422 and {d["field"] for d in r.json()["error"]["details"]} >= {"email", "password"}
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 200
    assert client.get("/api/auth/session").json()["user"]["name"] == "Ann"  # cookie session
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/session").json() == {"user": None}
    assert client.get("/api/projects", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_login_rate_limit(client):
    register(client, "rl@example.com")
    codes = [client.post("/api/auth/login", json={"email": "rl@example.com", "password": "wrong-pass"}).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_project_validation_and_planned_stages(client, owner):
    assert client.post("/api/projects", json=PROJECT | {"target_completion_date": "2024-01-01"}, headers=owner).status_code == 422
    assert client.post("/api/projects", json=PROJECT | {"unexpected": 1}, headers=owner).status_code == 422
    assert client.post("/api/projects", json=PROJECT | {"construction_type": "castle"}, headers=owner).status_code == 422
    p = client.post("/api/projects", json=PROJECT, headers=owner).json()
    ms = p["milestones"]
    assert [m["key"] for m in ms][0] == "site_preparation" and abs(sum(m["weight"] for m in ms) - 1) < 1e-9
    assert ms[0]["planned_start"] == "2025-01-01" and ms[-1]["planned_end"] == "2026-01-01"
    assert all(a["planned_end"] == b["planned_start"] for a, b in zip(ms, ms[1:]))  # back-to-back windows
    assert p["summary"]["progress"] is None and p["summary"]["forecast"]["status"] == "schedule_only"
    assert client.get("/api/projects", headers=owner).json()[0]["id"] == p["id"]


def test_projects_are_private(client, owner, project):
    other = register(client, "other@example.com", "Otto")
    pid = project["id"]
    assert client.get(f"/api/projects/{pid}", headers=other).status_code == 404  # existence not revealed
    assert client.get("/api/projects", headers=other).json() == []
    assert upload(client, pid, other, jpeg(scene(0)), "2025-02-01").status_code == 404
    obs = upload(client, pid, owner, jpeg(scene(0)), "2025-02-01").json()
    assert client.get(obs["image"]["url"], headers=other).status_code == 404
    assert client.get(f"/api/observations/{obs['id']}/report.pdf", headers=other).status_code == 404
    assert client.delete(f"/api/projects/{pid}", headers=other).status_code == 404
    client.db.users.update_one({"email": "other@example.com"}, {"$set": {"role": "admin"}})
    assert client.get(f"/api/projects/{pid}", headers=other).status_code == 200  # admins see every project


def test_upload_validation(client, owner, project):
    pid = project["id"]
    assert upload(client, pid, owner, b"definitely not an image", "2025-02-01").status_code == 415
    assert upload(client, pid, owner, b"", "2025-02-01").status_code == 422
    assert upload(client, pid, owner, jpeg(scene(0)), "2999-01-01").status_code == 422
    big = np.random.default_rng(0).integers(0, 255, (1400, 1400, 3), dtype=np.uint8)
    assert upload(client, pid, owner, jpeg(big, 100), "2025-02-01").status_code == 413  # limit is 2 MB in tests
    r = client.post(f"/api/projects/{pid}/observations", headers=owner, files={"file": ("a.jpg", jpeg(scene(0)), "image/jpeg")})
    assert r.status_code == 422  # capture_date is required


def test_analysis_failure_is_recorded_not_faked(client, owner, project, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(workflow.pipeline, "analyze", boom)
    obs = upload(client, project["id"], owner, jpeg(scene(0)), "2025-02-01").json()
    assert obs["status"] == "analysis_failed" and "RuntimeError" in obs["analysis_error"]
    assert obs["analysis"] is None and obs["result"] is None


def test_without_trained_profiles_the_photo_is_still_measured(client, owner, project, monkeypatch):
    monkeypatch.setattr(workflow, "reference_samples", lambda: [])
    obs = upload(client, project["id"], owner, jpeg(scene(0)), "2025-02-01").json()
    assert obs["status"] == "analyzed" and obs["stage_suggestion"] is None
    assert len(obs["analysis"]["steps"]) == 18 and "python -m app.cv.train" in obs["analysis"]["note"]


def test_photo_analysis_pipeline_result_and_explanation(client, owner, project):
    pid = project["id"]
    obs = upload(client, pid, owner, demo("building_6_structure-formwork.jpg"), "2025-07-01").json()
    assert obs["status"] == "analyzed"
    steps = obs["analysis"]["steps"]
    assert [s["number"] for s in steps] == list(range(1, 20))
    assert steps[-1]["key"] == "classification" and len(steps[-1]["metrics"]["nearest_photos"]) == 5
    assert all(s["image_url"] and s["algorithm"] and s["purpose"] for s in steps)
    assert client.get(steps[11]["image_url"], headers=owner).headers["content-type"] == "image/jpeg"
    assert obs["analysis"]["prediction"]["phase"] in phase_model.PHASES
    sug = obs["stage_suggestion"]
    assert sug["stage_key"] in [m["key"] for m in project["milestones"]] and 0 <= sug["stage_progress"] <= 100
    assert obs["result"]["used"]["source"] == "cv_suggestion"
    assert obs["result"]["forecast"]["status"] in ("estimated", "insufficient_data", "completed")
    titles = [s["title"] for s in obs["explanation"]]
    assert titles[0] == "1. The path this photo took through the pipeline" and titles[-1] == "8. Completion date"
    assert len(titles) == 8
    assert [r[0] for r in obs["explanation"][0]["rows"]] == [f"{s['number']}. {s['title']}" for s in steps]
    assert len(obs["explanation"][1]["rows"]) == 15

    pdf = client.get(f"/api/observations/{obs['id']}/report.pdf", headers=owner)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 100_000
    # no stored file may end in .jpg (anti-ransomware tools kill a process that deletes many of them)
    keys = [a["storage_key"] for a in client.db.image_assets.find({"observation_id": obs["id"]})]
    assert len(keys) == 21 and not any(k.endswith(".jpg") for k in keys)

    # confirming overrides the suggestion everywhere and the model learns from it
    confirmed = client.put(f"/api/observations/{obs['id']}/review", json={"stage_key": "structural_frame", "stage_progress": 40},
                           headers=owner).json()
    assert confirmed["result"]["used"] == {"source": "confirmed", "stage_key": "structural_frame", "stage_index": 2,
                                           "stage_name": "Structural frame", "stage_progress": 40}
    assert confirmed["result"]["progress"] == 0.39
    nxt = upload(client, pid, owner, demo("building_5_structure-rebar.jpg"), "2025-08-01").json()
    assert next(s for s in nxt["analysis"]["steps"] if s["key"] == "classification")["params"]["of_which_your_confirmed_photos"] == 1


def test_change_detection_between_photos_of_the_same_view(client, owner, project):
    pid = project["id"]
    first = scene(1)
    later = cv2.warpPerspective(first, np.linalg.inv(H_SHIFT), (640, 480), borderValue=(90, 90, 90))
    cv2.rectangle(later, (250, 180), (390, 300), (10, 200, 240), -1)
    upload(client, pid, owner, jpeg(first), "2025-03-01")
    o2 = upload(client, pid, owner, jpeg(later), "2025-05-01").json()
    step = next(s for s in o2["analysis"]["steps"] if s["key"] == "change")
    assert step["metrics"]["same_viewpoint"] is True and step["metrics"]["days_since_previous"] == 61
    assert step["metrics"]["changed_area_share"] > 0.03 and o2["summary"]["changed_area_share"] > 0.03


def test_full_journey(client, owner, project, settings):
    pid = project["id"]
    o1 = upload(client, pid, owner, jpeg(scene(1)), "2025-03-01").json()
    assert o1["status"] == "analyzed"
    assert client.get(o1["image"]["url"], headers=owner).status_code == 200
    assert client.get(o1["image"]["url"]).status_code == 401  # files need authentication
    assert upload(client, pid, owner, jpeg(scene(1)), "2025-03-01").status_code == 409  # exact duplicate

    # no confirmed stage yet → the project forecast is only the planned target
    fc = client.get(f"/api/projects/{pid}/forecast", headers=owner).json()
    assert fc["status"] == "schedule_only" and fc["estimated_completion_date"] == "2026-01-01"

    # confirm stages on two photos → weighted progress snapshots
    assert client.put(f"/api/observations/{o1['id']}/review", json={"stage_key": "nope"}, headers=owner).status_code == 422
    client.put(f"/api/observations/{o1['id']}/review", json={"stage_key": "foundation", "stage_progress": 40}, headers=owner)
    o2 = upload(client, pid, owner, jpeg(scene(2)), "2025-05-01").json()
    client.put(f"/api/observations/{o2['id']}/review", json={"stage_key": "structural_frame", "stage_progress": 10}, headers=owner)
    prog = client.get(f"/api/projects/{pid}/progress", headers=owner).json()
    assert [s["progress"] for s in prog["snapshots"]] == [0.16, 0.285]  # 0.10 + 0.15×0.4, then 0.25 + 0.35×0.1
    assert prog["planned_curve"]["basis"] == "milestones"

    fc = client.get(f"/api/projects/{pid}/forecast", headers=owner).json()
    assert fc["status"] == "estimated" and fc["latest_progress"] == 0.285 and fc["inputs"]["n_snapshots"] == 2
    assert {m["key"] for m in fc["methods"]} == {"earned_schedule", "velocity"}
    listed = client.get(f"/api/projects/{pid}/observations", headers=owner).json()
    assert [o["id"] for o in listed] == [o2["id"], o1["id"]]
    summary = client.get(f"/api/projects/{pid}", headers=owner).json()["summary"]
    assert summary["photos"] == 2 and summary["progress"] == 0.285 and summary["forecast"]["status"] == "estimated"

    pdf = client.get(f"/api/projects/{pid}/report.pdf", headers=owner)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # deleting a photo recomputes progress; deleting the project removes everything
    assert client.delete(f"/api/observations/{o2['id']}", headers=owner).status_code == 204
    assert [s["progress"] for s in client.get(f"/api/projects/{pid}/progress", headers=owner).json()["snapshots"]] == [0.16]
    assert client.delete(f"/api/projects/{pid}", headers=owner).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=owner).status_code == 404
    assert client.db.observations.count_documents({"project_id": pid}) == 0
    assert client.db.image_assets.count_documents({"project_id": pid}) == 0
    assert not (settings.storage_dir / "projects" / pid).exists()


def test_reports_handle_markup_characters_in_user_text(client, owner):
    body = {**PROJECT, "name": "Tower <A> & Co", "location": "Block <7>", "description": "Slab < beam & column"}
    pid = client.post("/api/projects", json=body, headers=owner).json()["id"]
    obs = upload(client, pid, owner, jpeg(scene(2)), "2025-07-01", filename="a<b>&c.jpg").json()
    for url in (f"/api/projects/{pid}/report.pdf", f"/api/observations/{obs['id']}/report.pdf"):
        pdf = client.get(url, headers=owner)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_forecast_preview_from_one_photo_saves_nothing(client, owner, project):
    pid = project["id"]
    obs = upload(client, pid, owner, jpeg(scene(0)), "2025-07-01").json()
    before = {c: client.db[c].count_documents({}) for c in ("progress_snapshots", "observations", "analysis_results")}

    body = {"observation_id": obs["id"], "stage_key": "structural_frame"}
    r = client.post(f"/api/projects/{pid}/forecast/preview", json=body, headers=owner).json()
    assert r["stage_name"] == "Structural frame"
    lo, hi = r["scenarios"]  # unknown stage fraction → start-of-stage and end-of-stage scenarios
    assert (lo["stage_progress"], lo["progress"]) == (0.0, 0.25)
    assert (hi["stage_progress"], hi["progress"]) == (100.0, 0.6)
    assert lo["forecast"]["status"] == hi["forecast"]["status"] == "estimated"
    assert hi["forecast"]["estimated_completion_date"] < lo["forecast"]["estimated_completion_date"]

    one = client.post(f"/api/projects/{pid}/forecast/preview", json=body | {"stage_progress": 50}, headers=owner).json()
    assert len(one["scenarios"]) == 1 and one["scenarios"][0]["progress"] == 0.425
    assert {c: client.db[c].count_documents({}) for c in before} == before  # preview is read-only
    assert client.db.observations.find_one({"_id": obs["id"]})["stage_review"] is None

    assert client.post(f"/api/projects/{pid}/forecast/preview", json=body | {"stage_key": "nope"}, headers=owner).status_code == 422
    other = register(client, "viewer@example.com")
    assert client.post(f"/api/projects/{pid}/forecast/preview", json=body, headers=other).status_code == 404


def test_planned_dates_are_respected_by_today(client, owner):
    p = client.post("/api/projects", json=PROJECT | {"planned_start_date": "2020-01-01", "target_completion_date": "2021-01-01"},
                    headers=owner).json()
    fc = client.get(f"/api/projects/{p['id']}/forecast", headers=owner).json()
    assert fc["status"] == "schedule_only" and fc["target_completion_date"] < date.today().isoformat()
