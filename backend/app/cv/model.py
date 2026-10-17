"""Construction-phase classifier on CV feature vectors (method phase-knn/v1). No neural network.

Training data = the 15-number feature vector (pipeline.py) of every labelled reference photo, plus the
photos the user has confirmed. Features are standardised (z-scores) so each one counts equally.

Phase decision — distance-weighted k-nearest neighbours (k = 5): find the 5 most similar photos
(smallest RMS distance) and let each vote for its phase with weight 1 / distance.

Phase profiles — the average standardised vector of each phase. They give the distance chart and the
position within the phase: each profile stands for the middle of its phase; the photo is projected towards
the next phase's profile (t_next) and the previous phase's profile (t_prev):
position = 0.5 + 0.5·t_next − 0.5·t_prev, clipped to 5–95 %.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np

from ..core.paths import CONFIG_DIR
from .pipeline import FEATURES

METHOD = "phase-knn/v1"
K = 5
PHASES = ["earthwork", "foundation", "structure", "finishing"]
PHASE_LABELS = {"earthwork": "Earthwork / site preparation", "foundation": "Foundation",
                "structure": "Structure (frame & walls)", "finishing": "Finishing & facade"}
REFERENCE_FILE = CONFIG_DIR / "reference_features.json"
MIN_STD = 0.02  # a feature that barely varies must not dominate the distance


@dataclass(frozen=True)
class Sample:
    phase: str
    vector: tuple[float, ...]
    source: str  # "reference" or "confirmed photo"
    ref: str = ""  # reference file (phase/name.jpg) or observation id


def vector_of(features: dict) -> tuple[float, ...]:
    return tuple(float(features[k]) for k in FEATURES)


class PhaseModel:
    def __init__(self, samples: list[Sample]):
        if not samples:
            raise ValueError("no training samples")
        self.samples = samples
        X = np.array([s.vector for s in samples], dtype=np.float64)
        self.mean = X.mean(axis=0)
        self.std = np.maximum(X.std(axis=0), MIN_STD)
        self.Z = (X - self.mean) / self.std
        self.labels = np.array([s.phase for s in samples])
        self.counts = {p: int((self.labels == p).sum()) for p in PHASES}
        self.phases = [p for p in PHASES if self.counts[p]]
        self.centroids = {p: self.Z[self.labels == p].mean(axis=0) for p in self.phases}

    @staticmethod
    def _dist(a: np.ndarray, b: np.ndarray) -> np.ndarray | float:
        return np.sqrt(np.mean((a - b) ** 2, axis=-1))

    def predict(self, vector) -> dict:
        z = (np.asarray(vector, dtype=np.float64) - self.mean) / self.std
        d = self._dist(self.Z, z)
        nearest = np.argsort(d)[:K]
        votes = {p: 0.0 for p in self.phases}
        for i in nearest:
            votes[self.labels[i]] += 1.0 / (d[i] + 1e-6)
        best = max(votes, key=votes.get)
        share = votes[best] / max(1e-9, sum(votes.values()))
        count_best = int(sum(self.labels[i] == best for i in nearest))

        def toward(other: str | None) -> float:
            if other not in self.centroids:
                return 0.0
            c, v = self.centroids[best], self.centroids[other] - self.centroids[best]
            return float(np.clip(np.dot(z - c, v) / max(1e-9, np.dot(v, v)), 0, 1))

        k = PHASES.index(best)
        t_next = toward(PHASES[k + 1] if k + 1 < len(PHASES) else None)
        t_prev = toward(PHASES[k - 1] if k > 0 else None)
        confidence = "medium" if count_best >= 4 and share >= 0.7 else "low"
        notes = [] if confidence == "medium" else [
            f"The 5 most similar photos are mixed ({', '.join(f'{PHASE_LABELS[p]} {sum(self.labels[i] == p for i in nearest)}' for p in self.phases if any(self.labels[i] == p for i in nearest))})."]
        return {
            "method": METHOD, "phase": best, "phase_label": PHASE_LABELS[best], "confidence": confidence, "notes": notes,
            "votes": {p: round(v / max(1e-9, sum(votes.values())), 3) for p, v in votes.items()},
            "neighbours": [{"phase": str(self.labels[i]), "distance": round(float(d[i]), 3),
                            "source": self.samples[i].source, "ref": self.samples[i].ref} for i in nearest],
            "profile_distances": {p: round(float(self._dist(self.centroids[p], z)), 3) for p in self.phases},
            "position": round(float(np.clip(0.5 + 0.5 * t_next - 0.5 * t_prev, 0.05, 0.95)), 3),
            "toward_next": round(t_next, 3), "toward_previous": round(t_prev, 3), "references": dict(self.counts),
        }


# ------------------------------------------------------------------ reference data
@lru_cache(maxsize=4)
def _load(path_str: str, mtime: float) -> dict:  # mtime is part of the cache key: retraining reloads the file
    return json.loads(open(path_str, encoding="utf-8").read())


def load_reference_file() -> dict | None:
    if not REFERENCE_FILE.exists():
        return None
    return _load(str(REFERENCE_FILE), REFERENCE_FILE.stat().st_mtime)


def reference_samples() -> list[Sample]:
    data = load_reference_file()
    if not data or data.get("features") != FEATURES:
        return []
    return [Sample(s["phase"], tuple(s["vector"]), "reference", s["file"]) for s in data["samples"]]


def leave_one_out(samples: list[Sample]) -> dict:
    """Predict every photo with a model built (including standardisation) from all the other photos."""
    confusion = {p: {q: 0 for q in PHASES} for p in PHASES}
    correct = 0
    for i, s in enumerate(samples):
        predicted = PhaseModel(samples[:i] + samples[i + 1:]).predict(s.vector)["phase"]
        confusion[s.phase][predicted] += 1
        correct += predicted == s.phase
    per_phase = {p: round(confusion[p][p] / max(1, sum(confusion[p].values())), 3) for p in PHASES}
    adjacent = sum(confusion[p][q] for p in PHASES for q in PHASES if abs(PHASES.index(p) - PHASES.index(q)) <= 1)
    return {"method": "leave-one-out", "samples": len(samples), "accuracy": round(correct / max(1, len(samples)), 3),
            "within_one_phase": round(adjacent / max(1, len(samples)), 3), "recall_per_phase": per_phase,
            "confusion": confusion, "chance_level": round(1 / len(PHASES), 3),
            "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
