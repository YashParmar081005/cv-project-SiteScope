import pytest

from app.cv.model import PHASES
from app.services.stages import default_milestones, load_templates, phase_of, stage_from_phase


def project(kind: str) -> dict:
    return {"construction_type": kind, "milestones": default_milestones(kind)}


def test_templates_are_consistent():
    for name, t in load_templates().items():
        assert sum(s["weight"] for s in t["stages"]) == pytest.approx(1.0), name
        assert all(s["phase"] in PHASES for s in t["stages"]), name
        order = [PHASES.index(s["phase"]) for s in t["stages"]]
        assert order == sorted(order), f"{name}: stages must follow the phase order"


def test_phase_of():
    assert phase_of("residential_building", "structural_frame") == "structure"
    assert phase_of("road", "paving") == "finishing"
    assert phase_of("road", "unknown") is None


def test_single_stage_phase_maps_position_directly():
    s = stage_from_phase(project("residential_building"), "structure", 0.4)
    assert (s["stage_key"], s["stage_progress"]) == ("structural_frame", 40)


def test_phase_spanning_two_stages_is_split_by_weight():
    # residential 'finishing' = Walls & envelope (0.20) + MEP & finishing (0.20)
    p = project("residential_building")
    assert stage_from_phase(p, "finishing", 0.25)["stage_key"] == "envelope"
    assert stage_from_phase(p, "finishing", 0.25)["stage_progress"] == 50
    later = stage_from_phase(p, "finishing", 0.75)
    assert (later["stage_key"], later["stage_progress"]) == ("finishing", 50)
    assert later["phase_stages"] == ["Walls & envelope", "MEP & finishing"]


def test_bridge_structure_phase():
    # bridge 'structure' = Piers & abutments (0.25) + Girders & deck (0.32)
    s = stage_from_phase(project("bridge"), "structure", 0.6)
    assert s["stage_key"] == "superstructure" and 0 <= s["stage_progress"] <= 100


def test_phase_without_stages_returns_none():
    p = {"construction_type": "residential_building", "milestones": [{"key": "custom", "name": "Custom", "weight": 1.0}]}
    assert stage_from_phase(p, "earthwork", 0.5) is None
