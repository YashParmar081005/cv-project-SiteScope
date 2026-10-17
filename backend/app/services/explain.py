"""'How we got the answer': a step-by-step derivation of a photo's result with the real numbers.

Used by the photo analysis page and the analysis PDF so both show the same explanation.
"""
from __future__ import annotations

from ..cv.model import PHASE_LABELS
from ..cv.pipeline import FEATURES

FEATURE_MEANING = {
    "sky": "share of the photo that is sky (step 4)",
    "soil": "share of the site that is brown soil (step 5)",
    "vegetation": "share of green vegetation (step 5)",
    "concrete": "share of grey concrete / gravel (step 5)",
    "steel_dark": "share of dark steel, rebar or shadow (step 5)",
    "machinery": "share of yellow/orange machinery (step 5)",
    "edge_density": "amount of Canny edges, ×5 (step 11)",
    "vertical_lines": "length of vertical Hough lines (step 12)",
    "horizontal_lines": "length of horizontal Hough lines (step 12)",
    "rectangles": "rectangular contours ÷ 20 (step 13)",
    "corners": "Shi-Tomasi corners ÷ 4000 (step 14)",
    "texture_entropy": "LBP texture entropy (step 16)",
    "axis_frequency": "share of FFT energy on the vertical/horizontal axes (step 17)",
    "vertical_edge_share": "share of Sobel energy in vertical edges (step 9)",
    "orthogonality": "share of gradient energy that is horizontal or vertical (step 9)",
}


# Which measurements best summarise each step in the "path through the pipeline" table (default: the first two).
KEY_METRICS = {
    "materials": ["soil", "concrete", "steel_dark"],
    "kmeans": ["dominant_colours"],
    "hough": ["vertical", "horizontal"],
    "corners": ["shi_tomasi_corners"],
    "classification": ["phase", "confidence"],
    "change": ["same_viewpoint", "changed_area_share", "reason"],
}


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f} %"


def _short(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.3g}"
    if isinstance(v, list):
        return ", ".join(_short(x) for x in v[:3]) + (" …" if len(v) > 3 else "")
    if isinstance(v, dict):
        return ", ".join(f"{k} {_short(x)}" for k, x in list(v.items())[:2])
    return str(v)


def key_result(step: dict) -> str:
    """One short line with the step's most telling measurements."""
    metrics = step.get("metrics") or {}
    if step["key"] == "features":
        return f"{len(metrics)} numbers (the feature vector)"
    keys = [k for k in KEY_METRICS.get(step["key"], list(metrics)[:2]) if metrics.get(k) is not None]
    return "; ".join(f"{k.replace('_', ' ')} = {_short(metrics[k])}" for k in keys) or "output image"


def explain(project: dict, analysis: dict | None, used: dict | None, preview: dict | None) -> list[dict]:
    """Sections of {title, text, rows?} explaining measurement → phase → stage → progress → completion date."""
    if not analysis:
        return []
    sections = []
    n_steps = len(analysis["steps"])
    features = analysis["features"]
    sections.append({
        "key": "pipeline",
        "title": "1. The path this photo took through the pipeline",
        "text": f"In order, every step the photo passed through ({n_steps}), the algorithm used and its key result. "
                f"Steps 1–3 prepare the image, 4–17 measure the site, 18 builds the feature vector, 19 classifies the "
                f"construction phase" + (" and 20 compares the photo with the previous one." if n_steps > 19 else "."),
        "rows": [[f"{st['number']}. {st['title']}", st["algorithm"], key_result(st)] for st in analysis["steps"]],
    })
    sections.append({
        "title": "2. Measure the photo",
        "text": f"The photo went through {n_steps} computer-vision steps. Steps 4–17 each measured "
                f"something about the site; 15 of those measurements form the photo's feature vector:",
        "rows": [[k, f"{features[k]:.3f}", FEATURE_MEANING[k]] for k in FEATURES],
    })
    p = analysis.get("prediction")
    if not p:
        sections.append({"title": "3. Phase classification", "text": analysis.get("note") or "No phase profiles are trained yet."})
        return sections
    votes = sorted(p["votes"].items(), key=lambda kv: -kv[1])
    sections.append({
        "title": "3. Find the most similar training photos (k-nearest neighbours)",
        "text": f"The training set has {sum(p['references'].values())} labelled photos "
                f"({', '.join(f'{PHASE_LABELS[k]} {v}' for k, v in p['references'].items() if v)}). Every feature is "
                f"standardised (z-score) and the root-mean-square distance to each training photo is computed. The 5 nearest "
                f"photos vote for their phase, each with weight 1 ÷ distance:",
        "rows": [[f"#{i + 1} {PHASE_LABELS[n['phase']]}", f"{n['distance']:.3f}",
                  "your confirmed photo" if n["source"] != "reference" else f"reference photo {n['ref']}"]
                 for i, n in enumerate(p["neighbours"])],
    })
    sections.append({
        "title": "4. Count the votes",
        "text": "Vote shares: " + ", ".join(f"{PHASE_LABELS[k]} {v:.0%}" for k, v in votes if v > 0)
                + f" → predicted phase {PHASE_LABELS[p['phase']]}, confidence {p['confidence']}"
                + " (medium needs at least 4 of the 5 neighbours and 70 % of the vote)."
                + (" " + " ".join(p["notes"]) if p["notes"] else ""),
    })
    sections.append({
        "title": "5. How far into the phase",
        "text": f"The photo is projected towards the next phase's profile (t_next = {p['toward_next']:.2f}) and the previous "
                f"phase's profile (t_previous = {p['toward_previous']:.2f}). Position = 0.5 + 0.5 × {p['toward_next']:.2f} "
                f"− 0.5 × {p['toward_previous']:.2f} = {p['position']:.0%} of the {PHASE_LABELS[p['phase']]} phase.",
    })
    stage = p.get("stage")
    if stage:
        sections.append({
            "title": "6. From phase to project stage",
            "text": f"In this {project['construction_type'].replace('_', ' ')} the phase covers: {', '.join(stage['phase_stages'])}. "
                    f"Spreading {p['position']:.0%} over those stages by their weights gives {stage['stage_name']} at "
                    f"{stage['stage_progress']} % (the computer-vision suggestion).",
        })
    if used:
        source = ("You confirmed" if used["source"] == "confirmed" else "Using the computer-vision suggestion:")
        changed = (used["source"] == "confirmed" and stage and (used["stage_key"] != stage["stage_key"]
                                                               or used["stage_progress"] != stage["stage_progress"]))
        text = f"{source} {used['stage_name']} at {'an unknown %' if used['stage_progress'] is None else str(used['stage_progress']) + ' %'}."
        if changed:
            text += " This differs from the suggestion, so your confirmed values are used."
        snap = (preview or {}).get("snapshot")
        if snap:
            parts = [f"{b['name']} {b['weight']:.0%} × {b['completion']:.2f}" for b in snap["breakdown"] if b["completion"] > 0]
            text += f" Progress = Σ weight × completion = {' + '.join(parts) or '0'} = {_pct(snap['progress'])}."
            if snap.get("lower_bound"):
                text += " (Stage % unknown → counted as 0, a cautious lower bound.)"
        sections.append({"title": "7. Progress", "text": text})
    fc = (preview or {}).get("forecast")
    if fc:
        lines = []
        es = next((m for m in fc["methods"] if m["key"] == "earned_schedule"), None)
        if es and es["status"] == "ok":
            x = es["details"]
            lines.append(f"Earned Schedule: actual time AT = {x['actual_time_days']} days since the planned start; the plan "
                         f"reached this progress on day ES = {x['earned_schedule_days']}; planned duration PD = "
                         f"{x['planned_duration_days']} days; working speed SPI = ES ÷ AT = {x['spi_t']}. Estimated duration = "
                         f"AT + (PD − ES) ÷ SPI → {es['estimate_date']}.")
        elif es:
            lines.append(f"Earned Schedule not possible: {es.get('reason')}.")
        vel = next((m for m in fc["methods"] if m["key"] == "velocity"), None)
        if vel and vel["status"] == "ok":
            lines.append(f"Trend of the confirmed photos: {vel['details']['slope_per_30_days'] * 100:.1f} % progress per 30 days "
                         f"→ 100 % on {vel['estimate_date']}.")
        if fc["status"] == "estimated":
            lines.append(f"Result: estimated completion {fc['estimated_completion_date']}"
                         + (f" (range {fc['range']['earliest']} – {fc['range']['latest']})" if fc.get("range") else "")
                         + f", {abs(fc['predicted_delay_days'])} days {'after' if fc['predicted_delay_days'] > 0 else 'before'} "
                         f"the planned finish {fc['target_completion_date']}, confidence {fc['confidence']}.")
        else:
            lines.append(f"Result: {fc['status'].replace('_', ' ')}. " + " ".join(fc["warnings"][-1:]))
        sections.append({"title": "8. Completion date", "text": " ".join(lines)})
    return sections
