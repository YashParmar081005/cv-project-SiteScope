"""Transparent completion-time baseline (method forecast-baseline/v1). Pure functions, no I/O.

Two documented methods, reported separately and combined into a range:

1. Earned Schedule (Lipke 2003). ES = time at which the *planned* progress curve equals the
   latest reviewed progress; AT = actual time elapsed; SPI(t) = ES / AT.
   Independent estimate at completion: IEAC(t) = AT + (PD − ES) / PF with
   PF = SPI(t) ("current efficiency continues") and PF = 1 ("rest goes to plan").
2. Velocity trend. Ordinary least squares of reviewed progress vs. time over the recent window;
   remaining = (1 − progress) / slope, with an 80 % t-interval on the slope when n ≥ 3.

Branches: insufficient_data · schedule_only · estimated · stalled · completed.
Confidence is "low" or "medium" and is never "high": the baseline is not calibrated against
historical project outcomes. A single observation never yields more than "low".
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from scipy import stats

from .progress import Milestone, planned_at, planned_curve, planned_inverse

METHOD_VERSION = "forecast-baseline/v1"
VELOCITY_WINDOW_DAYS = 180
MIN_VELOCITY_SPAN_DAYS = 7
STALL_PER_30_DAYS = 0.005        # < 0.5 percentage points per 30 days counts as stalled
STALE_AFTER_DAYS = 30
COMPLETE_AT = 0.999


def _days(a: date, b: date) -> int:
    return (b - a).days


def _add(d: date, days: float) -> date:
    return d + timedelta(days=round(days))


def velocity_method(points: list[tuple[date, float]]) -> dict:
    """OLS trend of the cumulative-max progress envelope over the recent window."""
    method = {"key": "velocity", "name": "Velocity trend (OLS)"}
    latest_date = points[-1][0]
    window = [p for p in points if _days(p[0], latest_date) <= VELOCITY_WINDOW_DAYS]
    if len({d for d, _ in window}) < 2:
        window = points
    dates = sorted({d for d, _ in window})
    if len(dates) < 2 or _days(dates[0], dates[-1]) < MIN_VELOCITY_SPAN_DAYS:
        return method | {"status": "unavailable",
                         "reason": f"needs >= 2 reviewed snapshots spanning >= {MIN_VELOCITY_SPAN_DAYS} days"}
    envelope, best = [], 0.0
    for d, p in window:
        best = max(best, p)
        envelope.append((d, best))
    x = np.array([_days(window[0][0], d) for d, _ in envelope], dtype=float)
    y = np.array([p for _, p in envelope], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    ss_res, ss_tot = float(((y - fitted) ** 2).sum()), float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    details = {"n_points": len(x), "window_start": window[0][0].isoformat(), "window_end": latest_date.isoformat(),
               "slope_per_30_days": round(slope * 30, 4), "r2": None if r2 is None else round(r2, 3)}
    if slope * 30 < STALL_PER_30_DAYS:
        return method | {"status": "stalled", "details": details,
                         "reason": f"progress rate {slope * 30:.2%} per 30 days is below the stall threshold"}
    remaining = (1.0 - y[-1]) / slope
    result = method | {"status": "ok", "estimate_date": _add(latest_date, remaining), "remaining_days": round(remaining),
                       "details": details}
    if len(x) >= 3:
        se = math.sqrt(ss_res / (len(x) - 2) / float(((x - x.mean()) ** 2).sum()))
        tq = float(stats.t.ppf(0.9, len(x) - 2))
        lo, hi = slope - tq * se, slope + tq * se
        details["slope_interval_80_per_30_days"] = [round(lo * 30, 4), round(hi * 30, 4)]
        result["earliest_date"] = _add(latest_date, (1.0 - y[-1]) / hi)
        result["latest_date"] = _add(latest_date, (1.0 - y[-1]) / lo) if lo > 0 else None
    return result


def earned_schedule_method(curve, latest: date, progress: float) -> dict:
    method = {"key": "earned_schedule", "name": "Earned Schedule"}
    origin = curve[0][0]
    at = _days(origin, latest)
    pd = planned_inverse(curve, 1.0)
    if at <= 0:
        return method | {"status": "unavailable", "reason": "latest observation is before the planned start"}
    if progress <= 0:
        return method | {"status": "unavailable", "reason": "no earned progress yet"}
    es = planned_inverse(curve, progress)
    if es is None or not pd:
        return method | {"status": "unavailable", "reason": "planned curve never reaches the observed progress"}
    spi = es / at
    details = {"actual_time_days": at, "earned_schedule_days": round(es, 1), "planned_duration_days": round(pd),
               "spi_t": round(spi, 3), "schedule_variance_days": round(es - at),
               "planned_progress_at_latest": round(planned_at(curve, latest), 4)}
    if spi < 0.05:
        return method | {"status": "unavailable", "details": details, "reason": "SPI(t) below 0.05; extrapolation not meaningful"}
    ieac_spi = at + (pd - es) / spi
    ieac_plan = at + (pd - es)
    return method | {"status": "ok", "estimate_date": _add(origin, ieac_spi), "remaining_days": round(ieac_spi - at),
                     "plan_rate_date": _add(origin, ieac_plan), "details": details}


def forecast(*, planned_start: date | None, target: date | None, milestones: list[Milestone],
             snapshots: list[dict], today: date, latest_observation_date: date | None) -> dict:
    curve, plan_basis = planned_curve(milestones, planned_start, target)
    snaps = sorted(snapshots, key=lambda s: s["as_of_date"])
    out = {
        "method_version": METHOD_VERSION, "generated_for": today, "label": "model_estimate",
        "status": None, "estimated_completion_date": None, "range": None, "remaining_days": None,
        "primary_method": None, "confidence": "none", "target_completion_date": target,
        "predicted_delay_days": None, "latest_progress": None, "latest_progress_date": None,
        "planned_progress_at_latest": None, "spi_t": None, "schedule_variance_days": None,
        "conditional_date_if_resumed": None, "methods": [], "assumptions": [], "warnings": [],
        "inputs": {"n_snapshots": len(snaps), "plan_basis": plan_basis},
    }
    latest_review = snaps[-1]["as_of_date"] if snaps else None
    out["data_freshness"] = {
        "latest_observation_date": latest_observation_date, "latest_reviewed_date": latest_review,
        "days_since_observation": _days(latest_observation_date, today) if latest_observation_date else None,
        "days_since_review": _days(latest_review, today) if latest_review else None,
    }
    out["data_freshness"]["stale"] = latest_review is None or _days(latest_review, today) > STALE_AFTER_DAYS
    out["assumptions"].append("Progress values come from reviewed stage assessments and milestone records "
                              "(weighted-milestone/v1); the computer-vision stage is a suggestion until confirmed.")
    if plan_basis == "milestones":
        out["assumptions"].append("Planned curve: each milestone's weight is spread linearly over its planned dates.")
    elif plan_basis == "linear":
        out["assumptions"].append("Planned curve: linear from planned start to target (milestone dates incomplete).")

    if not snaps:
        if curve:
            out.update(status="schedule_only", estimated_completion_date=target, primary_method="planned_schedule")
            out["warnings"].append("No reviewed progress yet: the date shown is the user-entered target, not a prediction.")
        else:
            out["status"] = "insufficient_data"
            out["warnings"].append("No reviewed progress and no planned schedule: nothing to estimate from.")
        return out

    latest = snaps[-1]
    progress = latest["progress"]
    out.update(latest_progress=progress, latest_progress_date=latest["as_of_date"])
    if curve:
        out["planned_progress_at_latest"] = round(planned_at(curve, latest["as_of_date"]), 4)
    if latest.get("lower_bound"):
        out["warnings"].append("Latest progress is a lower bound (current-stage fraction not estimated).")

    if progress >= COMPLETE_AT:
        done = next(s["as_of_date"] for s in snaps if s["progress"] >= COMPLETE_AT)
        out.update(status="completed", estimated_completion_date=done, remaining_days=0,
                   primary_method="observed", confidence="medium")
        if target:
            out["predicted_delay_days"] = _days(target, done)
        out["assumptions"].append("Completion date is the first reviewed snapshot at 100 %.")
        return out

    points = [(s["as_of_date"], s["progress"]) for s in snaps]
    velocity = velocity_method(points)
    es = earned_schedule_method(curve, latest["as_of_date"], progress) if curve else \
        {"key": "earned_schedule", "name": "Earned Schedule", "status": "unavailable", "reason": "no planned schedule"}
    out["methods"] = [es, velocity]
    if es["status"] == "ok":
        out["spi_t"] = es["details"]["spi_t"]
        out["schedule_variance_days"] = es["details"]["schedule_variance_days"]
        out["assumptions"].append("Earned Schedule: PF = SPI(t) assumes current schedule efficiency continues; "
                                  "PF = 1 assumes remaining work follows the plan.")
    if velocity["status"] in ("ok", "stalled"):
        out["assumptions"].append(f"Velocity: linear trend of the cumulative-max progress over the last "
                                  f"{VELOCITY_WINDOW_DAYS} days of reviewed snapshots.")

    if velocity["status"] == "stalled":
        out["status"] = "stalled"
        out["warnings"].append(velocity["reason"] + "; no finite completion date is estimated.")
        if es["status"] == "ok":
            out["conditional_date_if_resumed"] = es["plan_rate_date"]
            out["warnings"].append("If work resumes at the planned rate, completion would be about "
                                   f"{es['plan_rate_date'].isoformat()} (conditional scenario).")
        out["confidence"] = "low"
        return out

    candidates = []
    if es["status"] == "ok" and 0.2 <= es["details"]["spi_t"] <= 5:
        primary = es
        candidates += [es["estimate_date"], es["plan_rate_date"]]
    elif velocity["status"] == "ok":
        primary = velocity
    else:
        primary = None
    if velocity["status"] == "ok":
        candidates.append(velocity["estimate_date"])
        candidates += [d for d in (velocity.get("earliest_date"), velocity.get("latest_date")) if d]
        if "earliest_date" in velocity and velocity.get("latest_date") is None:
            out["warnings"].append("Velocity interval includes zero growth: the upper bound is unbounded.")

    if primary is None:
        out["status"] = "insufficient_data"
        if es["status"] == "ok":
            spi = es["details"]["spi_t"]
            out["warnings"].append(f"Progress is {'far behind' if spi < 0.2 else 'far ahead of'} the plan (SPI(t) = {spi}); "
                                   "extrapolating a completion date from one observation would not be meaningful.")
        elif curve and es.get("reason") == "no earned progress yet":
            out["warnings"].append("No progress yet (the very start of the first stage), so no finish date can be projected.")
        elif curve:
            out["warnings"].append(f"No finish date can be projected: {es.get('reason', 'schedule comparison unavailable')}.")
        else:
            out["warnings"].append("Not enough reviewed history for a velocity trend and no usable planned schedule.")
        return out

    estimate = primary["estimate_date"]
    out.update(status="estimated", estimated_completion_date=estimate, primary_method=primary["key"],
               remaining_days=_days(latest["as_of_date"], estimate),
               range={"earliest": min(candidates), "latest": max(candidates)} if len(candidates) > 1 else None)
    if target:
        out["predicted_delay_days"] = _days(target, estimate)

    span = _days(snaps[0]["as_of_date"], latest["as_of_date"])
    agree = True
    if es["status"] == "ok" and velocity["status"] == "ok":
        remaining = max(1, out["remaining_days"])
        agree = abs(_days(es["estimate_date"], velocity["estimate_date"])) <= 0.25 * remaining
        if not agree:
            out["warnings"].append("Earned Schedule and velocity estimates disagree by more than 25 % of the remaining duration.")
    r2 = velocity.get("details", {}).get("r2") if velocity["status"] == "ok" else None
    medium = (len(snaps) >= 3 and span >= 30 and not out["data_freshness"]["stale"] and not latest.get("lower_bound")
              and agree and (r2 is None or r2 >= 0.8))
    out["confidence"] = "medium" if medium else "low"
    if len(snaps) == 1:
        out["warnings"].append("Based on a single reviewed observation; treat as indicative only.")
    if out["data_freshness"]["stale"]:
        out["warnings"].append(f"Latest reviewed progress is older than {STALE_AFTER_DAYS} days.")
    pd = planned_inverse(curve, 1.0) if curve else None
    if pd and out["remaining_days"] > 5 * pd:
        out["warnings"].append("Estimate extrapolates far beyond the planned duration.")
    out["assumptions"].append("Confidence is capped at medium: the baseline is not calibrated against historical outcomes.")
    return out
