from datetime import date

import pytest

from app.services.progress import Milestone, Review, compute_snapshots, planned_at, planned_curve, planned_inverse

M = [Milestone("m1", "site_preparation", "Site", 0.1), Milestone("m2", "foundation", "Foundation", 0.2),
     Milestone("m3", "structural_frame", "Frame", 0.4), Milestone("m4", "finishing", "Finishing", 0.3)]


def test_no_milestones_or_reviews_gives_no_snapshots():
    assert compute_snapshots([], [Review("o", date(2025, 1, 1), 0, 0.5)]) == []
    assert compute_snapshots(M, []) == []


def test_reviewed_stage_with_fraction():
    snaps = compute_snapshots(M, [Review("o1", date(2025, 3, 1), 2, 0.5)])
    assert len(snaps) == 1
    s = snaps[0]
    assert s["progress"] == pytest.approx(0.1 + 0.2 + 0.4 * 0.5)
    assert not s["lower_bound"]
    assert [b["completion"] for b in s["breakdown"]] == [1.0, 1.0, 0.5, 0.0]
    assert s["frontier_observation_id"] == "o1"


def test_missing_stage_fraction_is_lower_bound():
    s = compute_snapshots(M, [Review("o1", date(2025, 3, 1), 2, None)])[0]
    assert s["progress"] == pytest.approx(0.3)
    assert s["lower_bound"] is True
    assert any("lower bound" in n for n in s["notes"])


def test_earlier_stage_review_does_not_reduce_progress_and_is_noted():
    snaps = compute_snapshots(M, [Review("a", date(2025, 3, 1), 2, 0.5), Review("b", date(2025, 4, 1), 1, 0.9)])
    assert [s["progress"] for s in snaps] == [pytest.approx(0.5), pytest.approx(0.5)]
    assert any("more advanced stage is kept" in n for n in snaps[1]["notes"])


def test_progress_is_monotonic_over_time():
    snaps = compute_snapshots(M, [Review("a", date(2025, 3, 1), 1, 0.5), Review("b", date(2025, 5, 1), 2, 0.2),
                                  Review("c", date(2025, 6, 1), 0, 1.0)])
    assert [s["as_of_date"] for s in snaps] == [date(2025, 3, 1), date(2025, 5, 1), date(2025, 6, 1)]
    values = [s["progress"] for s in snaps]
    assert values == sorted(values) and values[-1] == pytest.approx(0.1 + 0.2 + 0.4 * 0.2)


def test_same_day_reviews_use_most_advanced():
    s = compute_snapshots(M, [Review("a", date(2025, 3, 1), 1, 0.2), Review("b", date(2025, 3, 1), 2, 0.1)])[0]
    assert s["frontier_observation_id"] == "b"
    assert set(s["source_observation_ids"]) == {"a", "b"}


def test_completed_project_reaches_one():
    s = compute_snapshots(M, [Review("a", date(2025, 9, 1), 3, 1.0)])[0]
    assert s["progress"] == pytest.approx(1.0)


def test_out_of_range_stage_index_ignored():
    assert compute_snapshots(M, [Review("a", date(2025, 3, 1), 9, 0.5)]) == []


def test_planned_curve_linear_and_none():
    curve, basis = planned_curve(M, date(2025, 1, 1), date(2025, 12, 31))
    assert basis == "linear" and curve == [(date(2025, 1, 1), 0.0), (date(2025, 12, 31), 1.0)]
    assert planned_curve(M, None, None) == (None, None)
    assert planned_curve(M, date(2025, 1, 1), date(2024, 1, 1)) == (None, None)


def test_planned_curve_from_milestones():
    m = [Milestone("a", "a1", "A", 0.5, date(2025, 1, 1), date(2025, 1, 11)),
         Milestone("b", "b1", "B", 0.5, date(2025, 1, 11), date(2025, 1, 21))]
    curve, basis = planned_curve(m, date(2025, 1, 1), date(2025, 1, 21))
    assert basis == "milestones"
    assert planned_at(curve, date(2025, 1, 6)) == pytest.approx(0.25)
    assert planned_at(curve, date(2025, 1, 16)) == pytest.approx(0.75)
    assert planned_at(curve, date(2024, 12, 1)) == 0.0
    assert planned_at(curve, date(2026, 1, 1)) == pytest.approx(1.0)
    assert planned_inverse(curve, 0.75) == pytest.approx(15)
    assert planned_inverse(curve, 0.0) == 0.0
    assert planned_inverse(curve, 1.5) is None
