# SiteScope: Construction Completion Estimator (classical computer vision)

Add a construction project, upload dated site photos, and SiteScope estimates when it will be finished.
Each photo goes through a **classical computer-vision pipeline** (OpenCV + NumPy: colour spaces, CLAHE, filters,
HSV segmentation, k-means, Otsu/adaptive thresholds, morphology, Sobel, Laplacian, Canny, Hough, contours,
Harris/Shi-Tomasi corners, ORB, LBP, FFT). Its 15 measurements are classified into a construction phase by
**k-nearest neighbours** against 144 labelled reference photos. The phase becomes a suggested stage that you
confirm or adjust, and confirmed stages become weighted progress and a completion forecast (with a range and
a confidence level). No neural network is used.

Every photo has an analysis page and a **PDF report** showing each step (algorithm, purpose, parameters,
measurements, output image), the path the photo took through the pipeline, and how the answer was derived.

New here? Read [HOW_IT_WORKS.md](HOW_IT_WORKS.md) first: a plain-language walkthrough with a 5-minute demo
script. [BUILD_LOG.md](BUILD_LOG.md) records what was built, every decision, and the test results.

| Layer | Technology |
| --- | --- |
| Computer vision | OpenCV 5 (headless), NumPy, SciPy: 18-step pipeline + k-NN phase classifier + ORB/RANSAC change detection |
| Backend | FastAPI, Pydantic v2, PyMongo, JWT session cookie, ReportLab (PDF) |
| Database | MongoDB (metadata and results only; images are stored as files) |
| Frontend | Plain HTML + CSS + JavaScript modules, no build step, served by FastAPI |
| Tests | pytest (unit + API), `node --test` (form validation), Playwright (browser end-to-end) |
| Deployment | Docker, Docker Compose |

---

## 1. Run it locally (Windows)

Prerequisites: Python 3.11, MongoDB 7+, ~500 MB disk. Node 18+ only for the frontend tests.

```bash
cd "cv project"
copy .env.example .env                    # then set JWT_SECRET and ADMIN_PASSWORD

python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt

mongod --dbpath data\mongo                # if MongoDB is not already running as a service

cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open <http://localhost:8000>, create an account (or sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`;
the admin sees every project), then **+ Add project → Add a site photo**. Demo photos are in
[`demo_photos/`](demo_photos/).

Linux/macOS: use `backend/.venv/bin/python` and `cp` instead of `copy`.

## 2. Train the phase classifier (optional; trained features are included)

```bash
cd backend
python -m app.cv.train                         # reference_photos/<phase>/*.jpg → configs/reference_features.json
python -m app.cv.train --photos <folder>       # your own folder with earthwork/ foundation/ structure/ finishing/
```

Training runs the pipeline on every reference photo (without drawing images), stores the 15-number feature
vectors with their phase labels, and evaluates the classifier with **leave-one-out** cross-validation:
**59.0 %** exact-phase accuracy (chance: 25 %) and **91.7 %** within one phase on the 144 reference photos.
Per-phase recall and the confusion matrix are saved in `reference_features.json` under `evaluation`.

At run time the classifier also uses the photos **you** have confirmed (your account only), so it adapts to
your sites. Without any trained features the app still measures the photo and asks you to choose the stage.

**Reference photos:** 144 building-site photos from Wikimedia Commons under free licences (CC0, public domain,
CC BY, CC BY-SA), checked by eye against fixed phase definitions. Licence, author and source page of each file:
[`reference_photos/sources.csv`](reference_photos/sources.csv).

## 3. Docker

```bash
copy .env.example .env    # set JWT_SECRET (>= 32 characters) and ADMIN_PASSWORD
docker compose up --build # → http://localhost:8000
```

`app` serves the API and the frontend; `mongo` is reachable only inside the compose network. `./data` is
mounted, so uploaded photos and analysis images persist.

## 4. Configuration (`.env`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | development | `production` requires a `JWT_SECRET` of ≥ 32 characters |
| `MONGO_URI` / `MONGO_DB` | `mongodb://localhost:27017` / `sitescope` | database |
| `JWT_SECRET` | random per start in development | signs session tokens |
| `COOKIE_SECURE` | false | set true behind HTTPS |
| `ALLOW_REGISTRATION` | true | allow sign-up from the login page |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | — | administrator created at first start |
| `MAX_UPLOAD_MB` | 15 | photo size limit |
| `STORAGE_DIR` | `./data/storage` | where photos and analysis images are stored |

## 5. API (all under `/api`; interactive docs at `/docs`)

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | liveness |
| `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/session` | accounts and session (httpOnly cookie; Bearer token also accepted) |
| `GET POST /projects`, `GET DELETE /projects/{id}` | list, create, view, delete projects |
| `GET POST /projects/{id}/observations` | list photos / upload a photo (multipart: `file`, `capture_date`) → runs the CV pipeline |
| `GET DELETE /observations/{id}` | one photo with its analysis (every step), result and explanation / delete it |
| `GET /observations/{id}/report.pdf` | analysis report of one photo (all steps, images, how the answer was found) |
| `PUT /observations/{id}/review` | confirm the stage (`stage_key`, optional `stage_progress` 0–100) |
| `GET /projects/{id}/progress` | confirmed progress snapshots and the planned curve |
| `GET /projects/{id}/forecast` | estimated completion, range, confidence, assumptions |
| `POST /projects/{id}/forecast/preview` | what-if estimate for a photo's stage before saving (two scenarios if the % is unknown) |
| `GET /projects/{id}/report.pdf` | project report |
| `GET /files/{id}` | photo / thumbnail / step image (owner only) |

Errors always look like `{"error": {"code", "message", "details"}, "request_id"}`.

## 6. Tests

```bash
cd backend  && .venv\Scripts\python -m pytest        # unit (CV, k-NN, stages, progress, forecast) + API integration
cd frontend && npm install && npm test                # form validation
cd frontend && npx playwright test                    # browser test of the full journey (uses installed Edge)
```

The browser test starts its own server on port 8001 with a separate database (`sitescope_e2e`).

## 7. Security

* Passwords hashed with PBKDF2-SHA256 (600 000 rounds); sign-in rate limiting; session in an httpOnly,
  SameSite=Lax cookie.
* Each project belongs to the user who created it; other users get "not found" for it, its photos and reports.
* Uploads: streamed size limit, real-image check with a format allow-list, pixel limit, server-generated
  file names, duplicate rejection.
* Secrets only from the environment; strict Content-Security-Policy (scripts only from this server);
  all user text is HTML-escaped in the page and escaped in the PDF reports.

## 8. Operations

* Indexes are created at start-up. Logs are JSON with a request id (`LOG_JSON=true`).
* Backup: `mongodump --db sitescope --out backups/<date>` plus a copy of `data/storage/` (photos and analysis
  images); restore both together.
* Production: run behind HTTPS with `COOKIE_SECURE=true`.
* Stored JPEGs use the `.jpeg` extension. Some anti-ransomware tools (seen with 360 Total Security) kill a
  process that deletes many `.jpg` files, which would stop the server when a project is deleted.

## 9. Limitations

* Phase accuracy is 59 % exact / 92 % within one phase on the reference photos, so the stage is a
  **suggestion** that a person confirms. Finishing photos with scaffolding are often taken for structure.
* The reference photos are building sites. Road, rail and bridge photos are less reliable; if the predicted
  phase has no stage in that project type, the app asks you to choose the stage.
* Change detection only works for photos taken from roughly the same viewpoint; otherwise it says so.
* The completion forecast is a transparent baseline (Earned Schedule + trend). It is not calibrated against
  real finished projects, so confidence never goes above "medium".

## 10. Licences & attribution

* Reference photos: Wikimedia Commons contributors, licences per file in `reference_photos/sources.csv`
  (CC0, public domain, CC BY 2.0–4.0, CC BY-SA 2.0–4.0; share-alike photos remain under their licence).
* Demo photos: *Construction Site Safety*, Roboflow Universe Projects, **CC BY 4.0** (see `demo_photos/SOURCE.txt`).
* OpenCV (Apache 2.0), NumPy/SciPy (BSD), FastAPI (MIT), ReportLab (BSD).
