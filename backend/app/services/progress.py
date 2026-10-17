"""Weighted-milestone progress (method weighted-milestone/v1) and planned progress curves.

Progress at date t = Σ weight_i × completion_i(t) / Σ weight_i, where completion_i(t) is:
  1    if a reviewed observation captured <= t places the project at a later stage;
  f    for the stage a reviewed observation places the project in, where f is the reviewer's
       stage-completion fraction (0 if not given → the snapshot is flagged as a lower bound);
  0    otherwise.
The "frontier" is the most advanced reviewed stage up to t, so photos of a less advanced area
or a different viewpoint never reduce progress; such conflicts are reported as notes.
Only reviewed observations count. Unreviewed CV suggestions never produce a percentage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

METHOD = "weighted-milestone/v1"


@dataclass(frozen=True)
class Milestone:
    id: str
    key: str
    name: str
    weight: float
    planned_start: date | None = None
    planned_end: date | None = None


@dataclass(frozen=True)
class Review:
    observation_id: str
    capture_date: date
    stage_index: int
    stage_progress: float | None  # 0..1 within the stage, None when the reviewer did not estimate it


def compute_snapshots(milestones: list[Milestone], reviews: list[Review]) -> list[dict]:
    total_weight = sum(m.weight for m in milestones)
    if not milestones or total_weight <= 0:
        return []
    reviews = [r for r in reviews if 0 <= r.stage_index < len(milestones)]
    dates = sorted({r.capture_date for r in reviews})
    snapshots, frontier = [], None
    for t in dates:
        notes = []
        todays = [r for r in reviews if r.capture_date == t]
        for r in todays:
            if frontier and r.stage_index < frontier.stage_index:
                notes.append(f"Observation {r.observation_id[:8]} was reviewed as '{milestones[r.stage_index].name}', "
                             f"earlier than the previously reviewed '{milestones[frontier.stage_index].name}'; "
                             "the more advanced stage is kept (different area or viewpoint).")
            if frontier is None or (r.stage_index, r.stage_progress or 0.0) > (frontier.stage_index, frontier.stage_progress or 0.0):
                frontier = r
        breakdown, lower_bound = [], False
        for i, m in enumerate(milestones):
            if frontier and i < frontier.stage_index:
                completion, source = 1.0, "reviewed_stage"
            elif frontier and i == frontier.stage_index:
                if frontier.stage_progress is None:
                    completion, source, lower_bound = 0.0, "reviewed_stage_no_fraction", True
                else:
                    completion, source = frontier.stage_progress, "reviewed_stage"
            else:
                completion, source = 0.0, None
            breakdown.append({"milestone_id": m.id, "key": m.key, "name": m.name, "weight": m.weight,
                              "completion": round(completion, 4), "source": source})
        if lower_bound:
            notes.append("Current-stage completion was not estimated by the reviewer; it is counted as 0, "
                         "so this value is a lower bound.")
        progress = sum(b["weight"] * b["completion"] for b in breakdown) / total_weight
        snapshots.append({
            "as_of_date": t,
            "progress": round(progress, 4),
            "method": METHOD,
            "basis": "reviewed",
            "lower_bound": lower_bound,
            "frontier_observation_id": frontier.observation_id if frontier else None,
            "source_observation_ids": sorted({r.observation_id for r in todays} | ({frontier.observation_id} if frontier else set())),
            "breakdown": breakdown,
            "notes": notes,
        })
    return snapshots


# ---------------------------------------------------------------- planned curve

def planned_curve(milestones: list[Milestone], planned_start: date | None, target: date | None):
    """Piecewise-linear planned progress: list of (date, fraction) breakpoints plus its basis.

    basis "milestones": every milestone has planned dates; each contributes its weight linearly
    across its window. basis "linear": straight line from planned start to target. None: no plan.
    """
    total = sum(m.weight for m in milestones)
    if milestones and total > 0 and all(m.planned_start and m.planned_end for m in milestones):
        windows = [(m.planned_start, max(m.planned_end, m.planned_start + timedelta(days=1)), m.weight) for m in milestones]
        points = sorted({d for s, e, _ in windows for d in (s, e)})
        if planned_start and planned_start < points[0]:
            points.insert(0, planned_start)

        def value(t: date) -> float:
            return sum(w * min(1.0, max(0.0, (t - s).days / (e - s).days)) for s, e, w in windows) / total

        return [(p, round(value(p), 6)) for p in points], "milestones"
    if planned_start and target and target > planned_start:
        return [(planned_start, 0.0), (target, 1.0)], "linear"
    return None, None


def planned_at(curve: list[tuple[date, float]], t: date) -> float:
    if t <= curve[0][0]:
        return curve[0][1]
    for (d0, v0), (d1, v1) in zip(curve, curve[1:]):
        if d0 <= t <= d1:
            span = (d1 - d0).days
            return v0 if span == 0 else v0 + (v1 - v0) * (t - d0).days / span
    return curve[-1][1]


def planned_inverse(curve: list[tuple[date, float]], fraction: float) -> float | None:
    """Days after curve[0] at which planned progress first reaches `fraction` (None if never)."""
    origin = curve[0][0]
    if fraction <= curve[0][1]:
        return 0.0
    for (d0, v0), (d1, v1) in zip(curve, curve[1:]):
        if v0 < fraction <= v1:
            return (d0 - origin).days + (fraction - v0) / (v1 - v0) * (d1 - d0).days
    return None
