"""Train the phase model on reference site photos and evaluate it.

    python -m app.cv.train                       # from backend/
    python -m app.cv.train --photos <folder>     # folder with earthwork/ foundation/ structure/ finishing/

For every photo: run the CV pipeline (without rendering) → 15-number feature vector. The vectors and their
phase labels are saved to configs/reference_features.json; the app builds the phase profiles from them
(plus the photos users confirm). Accuracy is measured with leave-one-out cross-validation.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

from ..core.paths import REFERENCE_PHOTOS_DIR
from .model import METHOD, PHASE_LABELS, PHASES, REFERENCE_FILE, Sample, leave_one_out, vector_of
from .pipeline import FEATURES, METHOD as PIPELINE_METHOD, analyze

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def train(photos_dir: Path = REFERENCE_PHOTOS_DIR, out_file: Path = REFERENCE_FILE) -> dict:
    samples, records = [], []
    for phase in PHASES:
        folder = photos_dir / phase
        files = sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXTS) if folder.is_dir() else []
        for path in files:
            img = cv2.imread(str(path))
            if img is None:
                print(f"  skipped unreadable {path.name}", file=sys.stderr)
                continue
            vector = vector_of(analyze(img, render=False).features)
            samples.append(Sample(phase, vector, "reference", f"{phase}/{path.name}"))
            records.append({"file": f"{phase}/{path.name}", "phase": phase, "vector": list(vector)})
    if len({s.phase for s in samples}) < 2:
        raise SystemExit(f"Need reference photos for at least two phases in {photos_dir}/<phase>/")
    evaluation = leave_one_out(samples)
    data = {"method": METHOD, "pipeline": PIPELINE_METHOD, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "features": FEATURES, "phases": PHASES, "counts": {p: sum(s.phase == p for s in samples) for p in PHASES},
            "samples": records, "evaluation": evaluation}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--photos", type=Path, default=REFERENCE_PHOTOS_DIR)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    data = train(args.photos)
    ev = data["evaluation"]
    print(f"Trained on {ev['samples']} photos: " + ", ".join(f"{PHASE_LABELS[p]} {n}" for p, n in data["counts"].items()))
    print(f"Leave-one-out accuracy {ev['accuracy']:.1%} (chance {ev['chance_level']:.0%}), "
          f"within one phase {ev['within_one_phase']:.1%}")
    print("Confusion matrix (rows = true phase, columns = predicted):")
    print(" " * 12 + "".join(f"{p[:10]:>11}" for p in PHASES))
    for p in PHASES:
        print(f"{p[:11]:<12}" + "".join(f"{ev['confusion'][p][q]:>11}" for q in PHASES) + f"   recall {ev['recall_per_phase'][p]:.0%}")
    print(f"Saved {REFERENCE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
