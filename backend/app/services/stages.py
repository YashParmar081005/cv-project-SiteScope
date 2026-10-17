"""Stage templates and the mapping from a CV phase prediction to a project stage."""
from __future__ import annotations

from functools import lru_cache

import yaml

from ..core.paths import CONFIG_DIR


@lru_cache
def load_templates() -> dict:
    with open(CONFIG_DIR / "stages.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["types"]


def default_milestones(project_type: str) -> list[dict]:
    return [{"key": s["key"], "name": s["name"], "weight": s["weight"]} for s in load_templates()[project_type]["stages"]]


def phase_of(project_type: str, stage_key: str) -> str | None:
    return next((s["phase"] for s in load_templates().get(project_type, {}).get("stages", []) if s["key"] == stage_key), None)


def stage_from_phase(project: dict, phase: str, position: float) -> dict | None:
    """Spread the position within a phase (0–1) over the project's stages of that phase, by weight.

    Example (residential): phase 'finishing' covers 'Walls & envelope' (0.20) and 'MEP & finishing' (0.20);
    position 0.25 → 25 % of 0.40 = 0.10 → Walls & envelope at 50 %.
    """
    stages = [(i, m) for i, m in enumerate(project["milestones"]) if phase_of(project["construction_type"], m["key"]) == phase]
    if not stages:
        return None
    total = sum(m["weight"] for _, m in stages)
    target, cumulative = position * total, 0.0
    for i, m in stages:
        if target <= cumulative + m["weight"] or (i, m) == stages[-1]:
            within = min(1.0, max(0.0, (target - cumulative) / m["weight"]))
            return {"stage_key": m["key"], "stage_index": i, "stage_name": m["name"],
                    "stage_progress": int(round(within * 100 / 5) * 5),
                    "phase_stages": [m2["name"] for _, m2 in stages]}
        cumulative += m["weight"]
    return None
