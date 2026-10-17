# BUILD LOG — Construction Progress Monitoring & Completion-Time Estimation (classical computer vision)

The single record of what was planned, built, verified and changed. Requirements: [prompt.md](prompt.md).
How to run: [README.md](README.md). Plain-language explanation and demo script: [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

Legend: ✅ done & verified · 🟡 in progress · ⬜ not started

---

## 1. Current state (2026-10-17)

| Area | Status |
| --- | --- |
| Simple flow: projects → add project → project page → **photo analysis page** (result, confirm, every CV step, "how we got the answer", PDF) | ✅ verified in Edge, 0 console errors |
| Classical CV pipeline: 18 steps (OpenCV + NumPy), no neural network | ✅ |
| Phase classifier: k-NN (k = 5) on 15 features, 144 labelled Wikimedia Commons photos + the user's confirmed photos | ✅ leave-one-out **59.0 %** (chance 25 %), **91.7 %** within one phase |
| Change detection between consecutive photos (ORB + RANSAC homography + differencing) | ✅ |
| Progress (weighted stages) and completion forecast (Earned Schedule + trend) | ✅ |
| PDF reports: per-photo analysis report and project report | ✅ |
| Tests: 56 backend · 4 frontend · 2 browser end-to-end | ✅ all passing |
| Docker / compose | ✅ `docker compose config` valid; image build not run (Docker daemon off on this machine) |

---

## 2. Environment & key decisions

| Item | Decision |
| --- | --- |
| Machine | Windows 11, 16 CPU cores, 15.6 GB RAM, no GPU |
| Python | isolated 3.11 venv `backend/.venv` (uv): OpenCV 5 (headless), NumPy, SciPy, FastAPI 0.143, PyMongo 4.19, ReportLab |
| Disk | C: had ~2 GB free → all caches redirected to `./.cache` on D: |
| Frontend | **Plain HTML + CSS + JS** at the user's request (the prompt suggested React/Vite/Tailwind); served by FastAPI, no build step |
| Scope | **Simple at the user's request**: one flow, nothing extra visible, dead code removed (§4) |
| Method | **Classical computer vision only** at the user's request ("no AI; use computer-vision fundamentals") (§4.3) |
| Antivirus | 360 Total Security on this machine kills a process that deletes more than ~4 `.jpg` files → stored JPEGs use `.jpeg` (§3.6) |

---

## 3. Build record

### 3.1 Foundation ✅

* FastAPI app factory, settings from `.env`, JSON logs with request ids, uniform error format, security headers + CSP.
* Accounts (PBKDF2, login rate limit, httpOnly cookie sessions), one owner per project, admin sees all.
* Upload: streamed size limit, real-image check, pixel limit, capture date not in the future, duplicate rejection
  (SHA-256 per project); images on disk (`data/storage`), metadata in MongoDB.

### 3.2 Computer-vision pipeline ✅ (`backend/app/cv/pipeline.py`, method `classical-cv/v1`)

Every photo is resized to 640 px wide and passes through:

| # | Step | Algorithms |
| --- | --- | --- |
| 1 | Resize & colour spaces | `resize` (INTER_AREA), BGR→Gray, BGR→HSV |
| 2 | Histogram & CLAHE | `calcHist`, `createCLAHE(2, 8×8)` |
| 3 | Noise reduction | Gaussian 5×5, median 5, bilateral 9/75/75 |
| 4 | Sky detection | HSV threshold → `connectedComponents` touching the top edge → closing |
| 5 | Colour segmentation | HSV thresholds (soil, concrete, vegetation, dark steel, machinery) + opening |
| 6 | K-means | `kmeans` k = 5, k-means++ |
| 7 | Thresholding | Otsu, adaptive Gaussian 31×31 |
| 8 | Morphology | erode, dilate, open, close; connected regions before/after |
| 9 | Sobel | gradients x/y, magnitude, vertical-edge share, orthogonality (±15° of 0°/90°) |
| 10 | Laplacian | variance (sharpness) |
| 11 | Canny | automatic thresholds 0.66 / 1.33 × median |
| 12 | Hough | `HoughLinesP`; vertical / horizontal / other line lengths |
| 13 | Contours | `findContours`, `approxPolyDP` (3 %), convex quadrilaterals = rectangles |
| 14 | Corners | Harris + Shi-Tomasi (up to 5,000) |
| 15 | ORB | 1,000 keypoints + descriptors |
| 16 | LBP | 8-neighbour Local Binary Patterns, histogram entropy |
| 17 | FFT | log-magnitude spectrum, energy share on the axes |
| 18 | Feature vector | 15 features, each scaled to 0–1 |

Each step records its algorithm, purpose, parameters, measurements and an output image (rendered with OpenCV,
no plotting library). The images are stored per photo (`…/steps/NN_key.jpeg`).

### 3.3 Phase classifier and training ✅ (`app/cv/model.py`, `app/cv/train.py`, method `phase-knn/v1`)

* 4 phases: earthwork, foundation, structure, finishing. Every project stage maps to one phase
  (`configs/stages.yaml`).
* **Reference dataset:** 144 building-site photos downloaded from Wikimedia Commons, each checked by eye against fixed
  phase definitions (earthwork 31, foundation 28, structure 51, finishing 34); licence, author and source page per
  file in `reference_photos/sources.csv` (CC0, public domain, CC BY, CC BY-SA).
* **Classifier:** z-score standardisation → RMS distance → 5 nearest neighbours vote with weight 1/distance.
  Confidence "medium" needs ≥ 4 of 5 neighbours and ≥ 70 % of the vote, otherwise "low". Position inside the phase
  from projections onto the neighbouring phase centroids. The user's confirmed photos are added to the training set
  (owner only).
* **Evaluation (leave-one-out, standardisation refit per fold):**

  | Phase | Recall | Confused with |
  | --- | --- | --- |
  | earthwork | 61 % | foundation 6, structure 6 |
  | foundation | 54 % | earthwork 6, structure 6 |
  | structure | 76 % | foundation 5, finishing 4 |
  | finishing | 35 % | structure 20 |
  | **all** | **59.0 %** exact, **91.7 %** within one phase | chance 25 % |

  Iterations: first version 43.1 %; rescaling saturated features (corners, axis frequency), adding orthogonality
  and distance weighting → 59.0 %. A first evaluation leaked the held-out photo into the standardisation; fixed by
  refitting per fold. Caveat: feature choices were tuned on the same leave-one-out, so new-photo accuracy is likely
  a little lower.

### 3.4 Analysis, result and explanation ✅ (`app/services/workflow.py`, `explain.py`)

* Step 19 (classification) image: vote bar chart + the 5 neighbour photos (uniform thumbnails) with distances.
* Step 20 (change, from the 2nd photo): ORB matching (ratio 0.75) → RANSAC homography (≥ 30 inliers, sane
  transform, overlap) → warp → absdiff → Otsu → morphology → changed-area share; different viewpoints are reported
  as such.
* Phase + position → stage + % spread by stage weights (`stages.stage_from_phase`).
* The result uses the confirmed review if there is one, otherwise the CV suggestion; progress and forecast are
  computed for it (preview, nothing saved until **Confirm & save**).
* "How we got the answer", 8 sections with the real numbers: 1 the path through the pipeline (step → algorithm → key
  result), 2 the 15 measurements, 3 the k-NN neighbours, 4 the votes, 5 position in the phase, 6 phase → stage,
  7 progress formula, 8 completion date (Earned Schedule formula + trend).
* Failures are recorded and shown ("analysis failed"), never replaced by made-up output.

### 3.5 Progress, forecast and reports ✅

* Progress `weighted-milestone/v1`: Σ weight × completion; the most advanced stage counts; unknown % = lower bound.
* Forecast `forecast-baseline/v1`: Earned Schedule (SPI(t), IEAC) + OLS trend with 80 % interval; branches
  *estimated / stalled / completed / insufficient data*; confidence never "high"; what-if preview endpoint.
* PDFs (ReportLab): **analysis report** per photo (result table, every step with image, parameters and measurements,
  "how we got the answer"; ≈ 13 pages, headings kept with their content) and **project report** (summary, chart,
  stages, latest photos). All dynamic text is XML-escaped (a project name with `<` or `&` no longer breaks the PDF).

### 3.6 Frontend ✅

* `index.html`, `css/style.css`, `js/app.js` (router), `api.js`, `ui.js`, `validation.js`, `charts.js`,
  `pages/{login,projects,new-project,project,photo}.js`.
* Project page: estimate card, progress chart, *Add a site photo* (→ opens the photo page), photo list
  (*Open analysis*, *Delete*), project PDF, delete project.
* Photo page: photo + CV summary, result card with live estimate and confirm/adjust, 18–20 step cards
  (parameter and measurement tables stacked so long values wrap), "How we got the answer" (pipeline path table first),
  two *Download analysis report (PDF)* buttons.
* **Deleting a project crashed the server** in the browser test: 360 Total Security terminates a process (exit
  code 0, no log) after it deletes ~4 `.jpg` files, by count not rate; `.jpeg`, `.png` and extension-less files are
  not affected. Fix: stored JPEGs use `.jpeg` (originals, thumbnails, step images; test added); the one existing
  photo's 20 files were copied to `.jpeg` and the database keys updated.

---

## 4. Change history

### 4.1 First version: YOLO detection (superseded)

A YOLO26n detector was fine-tuned on two CC BY 4.0 datasets (Construction Site Safety, 398 images; Excavators,
2,656 images) with a leakage-free dataset pipeline. v1 reached test mAP50 0.367. It detected **machines and
workers**, not structure, and the training photos were mostly machines, often in quarries or showrooms rather than
building sites. Backup: `D:\cv collage\cv-project-yolo-version-backup-2026-10-17.zip` (outside the project).

### 4.2 Simplification (user request)

A full-featured version (dashboard, explorer, compare tab, settings, members, audit log, map…) was reduced to one
simple flow and unused code removed (API 38 → 15 endpoints). Backup:
`D:\cv collage\cv-project-full-version-backup-2026-10-17.zip`.

### 4.3 Pivot to classical computer vision (user request)

The user asked for no AI, with the photo analysed by computer-vision fundamentals, trained on site photos, and
every algorithm shown with a downloadable report and a final "how we got the answer" section.

| Removed | Replaced by |
| --- | --- |
| `backend/ml/` (dataset preparation, YOLO training, registry), `services/inference.py`, configs `classes/datasets/train/train_v2.yaml`, torch + ultralytics dependencies, `CONF_THRESHOLD` / `MODELS_DIR` settings, models volume in Docker | `app/cv/` (pipeline, k-NN model, change detection, training CLI), `reference_photos/`, `configs/reference_features.json` |
| Evidence-rule stage suggestion from detected objects | phase classification → stage mapping |
| Inline analysis panel on the project page | dedicated photo analysis page + analysis PDF |

The existing user project (rail, one photo) was re-analysed with the new pipeline.

### 4.4 Clean-up of leftovers and unused code (user request)

| Removed | Notes |
| --- | --- |
| `data/raw/`, `data/datasets/` (3,452 YOLO training images), `models/` (weights, runs, registry) | ≈ 550 MB |
| torch, torchvision, ultralytics and 30 other packages only they needed (`backend/.venv` 1.2 GB → 352 MB) | `opencv-python` (pulled in by ultralytics) shared the `cv2` folder with `opencv-python-headless`, so the headless package was reinstalled |
| Their downloads in `.cache/uv` (832 MB) and the `.cache/ultralytics`, `.cache/hf` folders | |
| Frontend: `classColor()` + box palette, `patch()`, the unused `query` option and error fields of the API helper; CSS for the detection-box viewer, chips and the grey badge | leftovers of the YOLO photo panel |
| Backend: unused `obs` parameter of `explain()`; unused `label` / `version` keys in `stages.yaml` | checked with vulture + ruff (remaining hits are framework callbacks) |
| `.gitignore` / `.dockerignore` entries for the deleted folders | |

---

## 5. Demo material

* `demo_photos/`: 6 building + 3 road photos (Roboflow *Construction Site Safety* test split, CC BY 4.0); none of
  them is among the reference photos (checked by SHA-256).
* The building demo story was run through the real system on a fresh account (HOW_IT_WORKS.md §8): CV phase right
  for photos 1–5, photo 6 (formwork) predicted as finishing and corrected by the user; final 42.5 % progress,
  estimated 20 Oct 2028, 203 days late, medium confidence. Road photos are mostly classified as "structure"
  (the reference set is building sites), so no stage is suggested for them.

---

## 6. Test results (latest run)

| Suite | Command | Result |
| --- | --- | --- |
| Backend unit + API (real CV pipeline, mongomock) | `cd backend && python -m pytest` | **56 passed** |
| Frontend validation | `cd frontend && npm test` | **4 passed** |
| Browser end-to-end (Edge, real pipeline, separate DB) | `cd frontend && npx playwright test` | **2 passed** |
| Docker | `docker compose config` | valid (build not executed: daemon off) |

---

## 7. Open items / next steps

* More reference photos (especially finishing and foundation) and road/rail/bridge photos would raise accuracy;
  add them under `reference_photos/<phase>/` and run `python -m app.cv.train`.
* To calibrate forecast confidence: dated progress of finished projects.
