"""Tests of the classical computer-vision pipeline, change detection and the phase classifier."""
import cv2
import numpy as np
import pytest

from app.cv import change
from app.cv.model import PHASES, PhaseModel, Sample, leave_one_out, reference_samples, vector_of
from app.cv.pipeline import FEATURES, analyze, working_image

from .conftest import DEMO_PHOTOS, scene


def solid(bgr, h=480, w=640):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = bgr
    noise = np.random.default_rng(0).integers(0, 12, (h, w, 3), dtype=np.uint8)
    return cv2.add(img, noise)


def grid_image():
    img = solid((150, 150, 150))
    for x in range(40, 640, 60):
        cv2.line(img, (x, 20), (x, 460), (30, 30, 30), 4)
    for y in range(40, 480, 70):
        cv2.line(img, (20, y), (620, y), (30, 30, 30), 4)
    return img


def test_pipeline_runs_all_steps_and_features_are_bounded():
    a = analyze(scene(3))
    keys = [s.key for s in a.steps]
    assert keys == ["colour_spaces", "histogram", "filters", "sky", "materials", "kmeans", "threshold", "morphology",
                    "sobel", "laplacian", "canny", "hough", "contours", "corners", "orb", "lbp", "fft", "features"]
    assert all(s.image is not None and s.image.ndim == 3 for s in a.steps)
    assert all(s.algorithm and s.purpose for s in a.steps)
    assert list(a.features) == FEATURES
    assert all(0.0 <= v <= 1.0 for v in a.features.values())


def test_pipeline_is_deterministic_and_render_free_mode_matches():
    img = scene(5)
    assert analyze(img).features == analyze(img, render=False).features
    assert all(s.image is None for s in analyze(img, render=False).steps)


def test_working_image_size():
    assert max(working_image(np.zeros((1200, 2000, 3), np.uint8)).shape[:2]) == 640


def test_sky_and_colour_segmentation():
    img = solid((60, 110, 160))                # brown soil (BGR)
    img[:200] = (235, 180, 120)                # blue sky on top
    f = analyze(img, render=False).features
    assert f["sky"] == pytest.approx(200 / 480, abs=0.05)
    assert f["soil"] > 0.8
    grey = analyze(solid((150, 150, 150)), render=False).features
    assert grey["concrete"] > 0.8 and grey["soil"] < 0.05


def test_hough_finds_structure_lines():
    lines = analyze(grid_image(), render=False).features
    blobs = analyze(scene(7), render=False).features
    assert lines["vertical_lines"] > 0.1 and lines["horizontal_lines"] > 0.1
    assert lines["orthogonality"] > blobs["orthogonality"]


def test_real_excavation_photo_is_mostly_soil():
    f = analyze(cv2.imread(str(DEMO_PHOTOS / "building_2_excavation.jpg")), render=False).features
    assert f["soil"] > 0.5 and f["vertical_lines"] < 0.1


H_TRUE = np.array([[0.98, -0.05, 25.0], [0.05, 0.98, -12.0], [0.0, 0.0, 1.0]])


def test_change_detection_aligns_and_measures_change():
    a = scene(1)
    b = cv2.warpPerspective(a, np.linalg.inv(H_TRUE), (640, 480), borderValue=(90, 90, 90))
    unchanged = change.compare(a, b, 30).metrics
    cv2.rectangle(b, (250, 180), (390, 300), (10, 200, 240), -1)
    changed = change.compare(a, b, 30)
    assert unchanged["same_viewpoint"] and changed.metrics["same_viewpoint"]
    assert changed.metrics["changed_area_share"] > unchanged["changed_area_share"]
    assert changed.metrics["changed_area_share"] > 0.03 and changed.image is not None


def test_change_detection_rejects_different_scenes():
    m = change.compare(scene(1), scene(2), 10).metrics
    assert m["same_viewpoint"] is False and "viewpoint" in m["reason"] or "matching" in m["reason"]


def toy_samples():
    rng = np.random.default_rng(0)
    centres = {p: np.full(len(FEATURES), 0.2 * (i + 1)) for i, p in enumerate(PHASES)}
    return [Sample(p, tuple(c + rng.normal(0, 0.02, len(FEATURES))), "reference", f"{p}/{k}.jpg")
            for p, c in centres.items() for k in range(6)]


def test_knn_predicts_nearest_phase_with_neighbours_and_position():
    model = PhaseModel(toy_samples())
    r = model.predict(tuple(np.full(len(FEATURES), 0.6)))  # the 'structure' cluster
    assert r["phase"] == "structure" and r["confidence"] == "medium"
    assert len(r["neighbours"]) == 5 and all(n["phase"] == "structure" for n in r["neighbours"])
    assert 0.05 <= r["position"] <= 0.95
    toward_finishing = model.predict(tuple(np.full(len(FEATURES), 0.68)))
    assert toward_finishing["position"] > r["position"]  # closer to the next phase → further into this phase


def test_leave_one_out_on_separable_data():
    ev = leave_one_out(toy_samples())
    assert ev["accuracy"] == 1.0 and ev["samples"] == 24


def test_trained_reference_file_matches_pipeline():
    samples = reference_samples()
    assert len(samples) >= 100 and {s.phase for s in samples} == set(PHASES)
    assert all(len(s.vector) == len(FEATURES) for s in samples)
    real = vector_of(analyze(cv2.imread(str(DEMO_PHOTOS / "building_6_structure-formwork.jpg")), render=False).features)
    assert PhaseModel(samples).predict(real)["phase"] in PHASES
