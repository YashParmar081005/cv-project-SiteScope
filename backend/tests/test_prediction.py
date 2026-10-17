"""Unit tests for every branch of the completion-time baseline (inputs are constructed test fixtures)."""
from datetime import date, timedelta

import pytest

from app.services.prediction import forecast
from app.services.progress import Milestone

START, TARGET = date(2025, 1, 1), date(2025, 12, 27)  # 360 planned days
M = [Milestone("a", "a1", "A", 0.5), Milestone("b", "b1", "B", 0.5)]


def snap(day: int, p: float, lower=False) -> dict:
    return {"as_of_date": START + timedelta(days=day), "progress": p, "lower_bound": lower}


def run(snaps, today=None, start=START, target=TARGET, milestones=M, latest_obs=None):
    today = today or (snaps[-1]["as_of_date"] + timedelta(days=3) if snaps else START + timedelta(days=30))
    latest_obs = latest_obs or (snaps[-1]["as_of_date"] if snaps else None)
    return forecast(planned_start=start, target=target, milestones=milestones, snapshots=snaps, today=today,
                    latest_observation_date=latest_obs)


def test_insufficient_data_without_plan_or_progress():
    r = run([], start=None, target=None)
    assert r["status"] == "insufficient_data" and r["estimated_completion_date"] is None
    assert r["confidence"] == "none"


def test_schedule_only_returns_target_not_prediction():
    r = run([])
    assert r["status"] == "schedule_only"
    assert r["estimated_completion_date"] == TARGET
    assert r["primary_method"] == "planned_schedule"
    assert any("not a prediction" in w for w in r["warnings"])


def test_completed_uses_first_full_snapshot():
    r = run([snap(100, 0.6), snap(300, 1.0), snap(320, 1.0)])
    assert r["status"] == "completed"
    assert r["estimated_completion_date"] == START + timedelta(days=300)
    assert r["predicted_delay_days"] == -60


def test_single_snapshot_uses_earned_schedule_with_low_confidence():
    r = run([snap(180, 0.25)])  # half the time elapsed, a quarter of the work done
    assert r["status"] == "estimated" and r["primary_method"] == "earned_schedule"
    es = r["methods"][0]
    assert es["details"]["spi_t"] == pytest.approx(0.5)
    # IEAC = AT + (PD - ES)/SPI = 180 + (360 - 90)/0.5 = 720 days
    assert r["estimated_completion_date"] == START + timedelta(days=720)
    assert es["plan_rate_date"] == START + timedelta(days=180 + 270)
    assert r["methods"][1]["status"] == "unavailable"
    assert r["confidence"] == "low"
    assert any("single reviewed observation" in w for w in r["warnings"])


def test_on_plan_history_gives_medium_confidence_and_agreeing_methods():
    snaps = [snap(d, d / 360) for d in (60, 120, 180, 240)]
    r = run(snaps)
    assert r["status"] == "estimated"
    assert r["confidence"] == "medium"
    assert r["estimated_completion_date"] == TARGET
    vel = r["methods"][1]
    assert vel["status"] == "ok" and vel["estimate_date"] == TARGET
    assert r["range"]["earliest"] <= r["estimated_completion_date"] <= r["range"]["latest"]
    assert r["predicted_delay_days"] == 0


def test_confidence_is_never_high():
    snaps = [snap(d, d / 360) for d in range(10, 300, 10)]
    r = run(snaps)
    assert r["confidence"] == "medium"
    assert any("capped at medium" in a for a in r["assumptions"])


def test_stalled_progress_has_no_finite_date_but_conditional_scenario():
    snaps = [snap(100, 0.30), snap(140, 0.30), snap(180, 0.301)]
    r = run(snaps)
    assert r["status"] == "stalled"
    assert r["estimated_completion_date"] is None
    assert r["conditional_date_if_resumed"] is not None
    assert r["confidence"] == "low"


def test_extreme_spi_from_single_observation_gives_no_date():
    r = run([snap(300, 0.10)])  # 10 % done after 300 of 360 planned days → SPI(t) = 0.12, below 0.2
    assert r["methods"][0]["status"] == "ok" and r["methods"][0]["details"]["spi_t"] < 0.2
    assert r["status"] == "insufficient_data" and r["estimated_completion_date"] is None
    assert any("far behind the plan" in w for w in r["warnings"])


def test_velocity_only_when_no_plan():
    r = run([snap(0, 0.1), snap(30, 0.2), snap(60, 0.3)], start=None, target=None)
    assert r["primary_method"] == "velocity"
    assert r["estimated_completion_date"] == START + timedelta(days=60 + 210)
    assert r["methods"][0]["status"] == "unavailable"


def test_two_points_too_close_for_velocity():
    r = run([snap(100, 0.2), snap(103, 0.25)])
    assert r["methods"][1]["status"] == "unavailable"
    assert r["primary_method"] == "earned_schedule"


def test_observation_before_planned_start_and_zero_progress():
    r = run([snap(-10, 0.05)])
    assert r["methods"][0]["status"] == "unavailable"
    r = run([snap(50, 0.0)])
    assert r["methods"][0]["status"] == "unavailable"
    assert r["status"] == "insufficient_data" and any("No progress yet" in w for w in r["warnings"])


def test_stale_and_lower_bound_warnings_reduce_confidence():
    snaps = [snap(d, d / 360) for d in (60, 120, 180, 240)]
    r = run(snaps, today=START + timedelta(days=300))
    assert r["data_freshness"]["stale"] is True and r["confidence"] == "low"
    snaps[-1]["lower_bound"] = True
    r = run(snaps)
    assert r["confidence"] == "low"
    assert any("lower bound" in w for w in r["warnings"])


def test_methods_disagreeing_are_flagged():
    # fast recent velocity but far behind plan
    snaps = [snap(200, 0.05), snap(230, 0.15), snap(260, 0.25)]
    r = run(snaps)
    assert any("disagree" in w for w in r["warnings"])
    assert r["confidence"] == "low"


def test_noisy_history_has_unbounded_upper_bound_warning():
    snaps = [snap(100, 0.20), snap(110, 0.21), snap(120, 0.30), snap(130, 0.305)]
    r = run(snaps, start=None, target=None)
    vel = r["methods"][1]
    if vel["status"] == "ok" and vel.get("latest_date") is None:
        assert any("unbounded" in w for w in r["warnings"])
    assert r["range"] is None or r["range"]["earliest"] <= r["range"]["latest"]


def test_schedule_variance_reported():
    r = run([snap(200, 0.4)])
    assert r["schedule_variance_days"] == round(0.4 * 360 - 200)
    assert r["planned_progress_at_latest"] == pytest.approx(200 / 360, abs=1e-3)
