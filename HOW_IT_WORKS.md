# How SiteScope Works

SiteScope estimates **when a construction project will be finished** from dated site photos.
You add a project with its planned dates and upload a site photo. **Classical computer vision** (OpenCV + NumPy, no
neural network) measures the photo, compares it with labelled reference photos to find the construction stage,
and the app turns that stage into progress and an estimated completion date. Every step, algorithm and
number is shown on the photo's analysis page and in a downloadable PDF report.

> Setup and commands: [README.md](README.md) · What was built and tested: [BUILD_LOG.md](BUILD_LOG.md)

---

## 1. The idea in one minute

| Question | Answered by | How |
| --- | --- | --- |
| What does the photo contain? | **CV pipeline** (17 steps) | Colours (soil, concrete, steel, vegetation, sky), edges, straight lines, rectangles, corners, texture, frequencies |
| Which construction phase is it? | **k-nearest neighbours** | The photo's 15 measurements are compared with 144 labelled reference photos; the 5 most similar vote |
| Which stage, how far along? | **Phase → stage rules** | The phase and the position inside it are spread over the project's stages by their weights |
| Is that right? | **You** | You can accept the suggestion or change the stage and % (the model then learns from your photo) |
| How much is done? | **Formula** | Each stage has a weight; finished stages + the current stage's share = progress |
| When will it finish? | **Forecast** | Progress is compared with the planned schedule (Earned Schedule) and the trend between photos |

**No AI model, no black box.** Each number comes from a named algorithm whose output you can see. The app
shows how confident it is and never presents a guess as a fact.

---

## 2. The screens

```
 ┌──────────────┐    ┌────────────────┐    ┌─────────────────────────────┐    ┌──────────────────────────────────────┐
 │ My projects  │ ─► │ Add project    │ ─► │ Project page                │ ─► │ Photo analysis page                  │
 │ cards with   │    │ name, type,    │    │ • estimated completion      │    │ • result: CV suggestion + estimate   │
 │ progress and │    │ location,      │    │ • progress chart            │    │ • confirm / adjust stage and %       │
 │ finish date  │    │ start, finish  │    │ • Add a site photo          │    │ • every CV step: algorithm, why,     │
 └──────────────┘    └────────────────┘    │ • photo list · PDF report   │    │   parameters, measurements, image    │
                                           └─────────────────────────────┘    │ • How we got the answer · PDF report │
                                                                              └──────────────────────────────────────┘
```

After **Analyse photo** the photo's analysis page opens:

1. **Result** (top right): *Computer vision suggests* a stage and % (e.g. *Foundation · 55 %*), and the
   estimated completion date if that suggestion is used.
2. **Confirm or adjust**: keep the suggestion or pick another stage, move the slider or tick *Not sure how much
   of this stage is done*. The estimate updates live. **Confirm & save** stores it.
3. **Computer-vision pipeline**: one card per step, showing the algorithm (OpenCV call), why it is used, its parameters,
   what it measured and its output image.
4. **How we got the answer**: the path the photo took through the pipeline (step → algorithm → key result),
   then the derivation from measurements → phase → stage → progress → completion date, with the real numbers.
5. **Download analysis report (PDF)**: the same content as a document.

---

## 3. The computer-vision pipeline (what happens to every photo)

```
 photo ─► 1 resize / colour spaces ─► 2 histogram + CLAHE ─► 3 noise filters ─► 4 sky removed
        ─► 5 colour segmentation ─► 6 k-means ─► 7 thresholds ─► 8 morphology            (colour & regions)
        ─► 9 Sobel ─► 10 Laplacian ─► 11 Canny ─► 12 Hough lines ─► 13 contours          (edges & shapes)
        ─► 14 Harris / Shi-Tomasi corners ─► 15 ORB keypoints ─► 16 LBP texture ─► 17 FFT  (points, texture, frequency)
        ─► 18 feature vector (15 numbers) ─► 19 k-NN phase classification ─► 20 change vs previous photo
```

| # | Step | Algorithm | What it tells us |
| --- | --- | --- | --- |
| 1 | Resize & colour spaces | `cv2.resize` (640 px), BGR → Gray, BGR → HSV | Every photo is measured at the same size; HSV separates colour from brightness |
| 2 | Histogram & CLAHE | `cv2.calcHist`, `cv2.createCLAHE(2, 8×8)` | Brightness distribution; local contrast so shadows and bright sky show detail |
| 3 | Noise reduction | Gaussian 5×5, median 5, bilateral 9/75/75 | Removes sensor noise before edge detection (bilateral keeps edges sharp) |
| 4 | Sky detection | HSV threshold → `connectedComponents` touching the top → closing | Sky is removed so later measurements describe only the site |
| 5 | Colour segmentation | HSV thresholds + opening | Share of **soil** (earthwork), **concrete**, **dark steel**/rebar, **vegetation**, yellow **machinery** |
| 6 | K-means clustering | `cv2.kmeans`, k = 5 | The 5 dominant colours of the scene and their shares |
| 7 | Thresholding | Otsu + adaptive Gaussian (31×31) | Global vs local foreground/background separation |
| 8 | Morphology | erode, dilate, open, close (5×5) | Cleans the binary image; counts how fragmented the scene is |
| 9 | Sobel gradients | `cv2.Sobel` x/y, magnitude, direction | Vertical vs horizontal edges; **orthogonality** (man-made structure is mostly 0°/90°) |
| 10 | Laplacian | `cv2.Laplacian` | Sharpness / fine texture (rough soil vs smooth surfaces) |
| 11 | Canny | `cv2.Canny`, thresholds from the median | **Edge density**: how much detail and structure the site contains |
| 12 | Hough lines | `cv2.HoughLinesP` | Long **vertical** and **horizontal** lines: columns, floors, formwork |
| 13 | Contours | `findContours`, `approxPolyDP`, `isContourConvex` | Convex 4-sided shapes = **rectangles** (openings, panels, slabs) |
| 14 | Corners | `cornerHarris`, `goodFeaturesToTrack` | Many corners = man-made structure (beams, scaffolding joints) |
| 15 | ORB keypoints | `cv2.ORB_create(1000)` | Distinctive points, used to match this photo with the previous one (step 20) |
| 16 | Local Binary Patterns | 8-neighbour LBP + histogram entropy | **Texture**: busy (soil, rubble, rebar) vs smooth (plaster, glass) |
| 17 | Fourier transform | `np.fft.fft2`, log magnitude | Repeating horizontal/vertical patterns (floors, windows) put energy on the axes |
| 18 | Feature vector | 15 numbers from steps 4–17, each 0–1 | The photo's "fingerprint" |
| 19 | Phase classification | k-nearest neighbours (k = 5) | Earthwork / Foundation / Structure / Finishing, see §4 |
| 20 | Change detection | ORB matching → RANSAC homography → warp → absdiff → Otsu → morphology | If two photos show the same view: the share of the area that changed |

Step 20 appears from the second photo of a project on. Photos taken from different spots are reported as
"different viewpoint" instead of producing a meaningless difference.

The 15 features: `sky, soil, vegetation, concrete, steel_dark, machinery, edge_density, vertical_lines,
horizontal_lines, rectangles, corners, texture_entropy, axis_frequency, vertical_edge_share, orthogonality`.

---

## 4. From 15 numbers to a construction phase (k-nearest neighbours)

1. **Standardise** each feature (z-score) using the training photos, so no feature dominates by scale.
2. **Distance** = root-mean-square difference between this photo's features and every training photo's.
3. The **5 nearest** training photos vote for their phase, each with weight 1 ÷ distance.
4. Highest vote share = predicted phase. Confidence is **medium** only if ≥ 4 of the 5 neighbours and ≥ 70 % of
   the vote agree; otherwise **low** (never "high").
5. **How far into the phase**: the photo is projected onto the line from this phase's average profile towards
   the next phase's (t_next) and the previous phase's (t_prev): position = 0.5 + 0.5·t_next − 0.5·t_prev.

The analysis page shows the 5 neighbour photos with their distances, so you can see *why* it decided.

**It learns from you:** every photo you confirm becomes a training photo for your next analyses (your account
only). Step 19 shows how many of your confirmed photos are in the training set.

### Training data and accuracy

* **144 reference photos** of building sites from **Wikimedia Commons** (free licences: CC0, public domain, CC BY,
  CC BY-SA), each checked by eye against fixed phase definitions:
  earthwork 31 · foundation 28 · structure 51 · finishing 34.
  Licence, author and source page of each photo: [`reference_photos/sources.csv`](reference_photos/sources.csv).
* Retrain after adding photos: `python -m app.cv.train` (from `backend/`). The features are saved in
  `backend/configs/reference_features.json`.
* **Leave-one-out evaluation** (each photo is classified by a model built from the other 143):

  | Measure | Result |
  | --- | --- |
  | Accuracy (exact phase) | **59.0 %** (guessing would give 25 %) |
  | Within one phase (e.g. foundation ↔ structure) | **91.7 %** |
  | Recall: earthwork / foundation / structure / finishing | 61 % / 54 % / 76 % / 35 % |

  Typical mistake: finishing photos taken while scaffolding is still up look like structure. Note that the
  feature choices were tuned with this same evaluation, so the real accuracy on new photos is probably a little lower.
  That is why the result is a *suggestion* that you confirm.

---

## 5. From phase to project stage

Each project type has stages with **weights** (share of the total work) and a phase. A residential building:

| Stage | Weight | Phase |
| --- | --- | --- |
| Site preparation & excavation | 10 % | earthwork |
| Foundation | 15 % | foundation |
| Structural frame | 35 % | structure |
| Walls & envelope | 20 % | finishing |
| MEP & finishing | 20 % | finishing |

The position inside the phase is spread over that phase's stages by weight. Example: *Finishing, 50 %* covers
Walls & envelope (20) + MEP & finishing (20); 50 % of 40 = 20 → **Walls & envelope 100 %**.

---

## 6. How progress is calculated

```
 progress = Σ weight × completion      completion = 1 for stages before the current stage
                                                  = the stage % for the current stage
                                                  = 0 for later stages
```

Example: **Structural frame, 40 % done** → 10 % + 15 % + 35 % × 0.40 = **39.0 %**.

* The most advanced confirmed stage counts, so a photo of a less finished corner never lowers progress.
* "Not sure how much of this stage is done" counts as 0 % (a cautious lower bound) and is marked as such.

---

## 7. How the completion date is estimated

**Earned Schedule** compares where the project **is** with where the **plan** said it would be:

```
 AT  = days since the planned start             (actual time)
 ES  = day on which the plan reached this progress   (earned schedule)
 SPI = ES ÷ AT                                   (working speed vs plan: 1 = on plan)
 estimated duration = AT + (planned duration − ES) ÷ SPI
```

**Trend**: with two or more confirmed photos, a straight line through the progress points is extended to 100 %.

* The **range** spans the dates from both methods.
* **Confidence** is *low* with one photo or old data, and *medium* with ≥ 3 photos over ≥ 30 days, a recent
  photo and methods that agree. Never *high*: the method has not been checked on real finished projects.
* Special cases are said in words: *No estimate yet*, *Not enough progress yet*, *Work has stalled*, *Completed*.

---

## 8. Presenting it to your teacher (≈ 5 minutes)

Use the photos in [`demo_photos/`](demo_photos/). They are **not** among the reference photos the classifier
learns from, so the results are genuine predictions.

**Before the class:** start the app (§ 9), open <http://localhost:8000> and create a **new account** (the
numbers below are for an account with no confirmed photos yet, because the model also learns from your photos).

**Step 1: add the project.** *+ Add project* → Name `Green Park Tower`, Type `Residential building`, Location
`Ahmedabad, Gujarat`, Start `1 Apr 2025`, Planned finish `31 Mar 2028`, details `14-storey residential tower,
120 flats` → **Create project**. Point out: "No estimate yet. We need a photo."

**Step 2: add the photos one by one** (choose file → set date → *Analyse photo* → set stage and % → *Confirm &
save* → *Back to project*):

| # | File | Date taken | Computer vision says | You set | Estimate after saving |
| --- | --- | --- | --- | --- | --- |
| 1 | `building_1_site-clearing.jpg` | 20 May 2025 | Earthwork (low) → Site preparation 60 % | Site preparation 50 % | 3 Dec 2027 (119 days early, low) |
| 2 | `building_2_excavation.jpg` | 15 Jul 2025 | Earthwork (**medium**) → Site preparation 50 % | Site preparation 90 % | 5 Jun 2028 (66 days late) |
| 3 | `building_3_foundation-digging.jpg` | 20 Sep 2025 | Foundation (low) → Foundation 55 % | Foundation 30 % | 27 Jun 2028 |
| 4 | `building_4_foundation-piling.jpg` | 15 Dec 2025 | Foundation (low, tie with structure) → Foundation 50 % | Foundation 80 % | 15 Jun 2028 |
| 5 | `building_5_structure-rebar.jpg` | 10 May 2026 | Structure (low) → Structural frame 50 % | Structural frame 20 % | 14 Sep 2028 |
| 6 | `building_6_structure-formwork.jpg` | 5 Oct 2026 | Finishing (low) → Walls & envelope 100 % ✗ | **Structural frame 50 %** (correct it) | **20 Oct 2028, 203 days late, medium confidence** |

Final: 42.5 % done, likely range 26 Jun 2028 – 23 Dec 2028, working at 84 % of the planned pace.
(These results came from running exactly these steps through the app.)

**What to show and say:**

* Photo 1: "The pipeline measured the photo (soil, edges, lines, texture…) and its nearest reference photos
  are mostly earthwork sites. One photo, so low confidence."
* Photo 3: scroll through its analysis page. Show **colour segmentation** (soil, concrete, steel shares),
  **Canny** edges, **Hough lines** (vertical in green, horizontal in orange) and the **5 nearest reference photos**
  in step 19. Then open **How we got the answer**: "This is the exact path the photo took and how each number was
  obtained." Click **Download analysis report (PDF)**.
* Photo 6: "The computer says finishing: in step 19 most of its nearest reference photos are finishing
  photos. It is wrong, this is formwork, so I correct it to Structural frame. A person stays in control, and
  the model learns from my correction."
* Back on the project page: six photos over 17 months, the schedule and the trend agree, confidence is
  medium, about 7 months behind plan. Show the chart (grey = plan, orange = confirmed, purple = estimate) and
  **Download project report (PDF)**.

**Tips**

* Confidence drops to *low* again if the newest photo is more than 30 days old on the day you present. If you
  present much later, set the last photo's date close to that day.
* The reference photos are building sites. Road, rail and bridge photos are often classified as "structure";
  if the project type has no stage for that phase, the app asks you to choose the stage yourself.
* Expected questions: *Why not deep learning?* With only 144 labelled photos, a neural network would overfit
  and could not explain its decision. Classical CV features plus k-NN are transparent and can be checked step by step.
  *Is the date guaranteed?* No: it's an estimate with a range and a confidence level, and the app says so.

---

## 9. Running it

```
# 1. MongoDB must be running (once):   mongod --dbpath "D:\cv collage\cv project\data\mongo"
# 2. Start the app:
cd "D:\cv collage\cv project\backend"
.venv\Scripts\python -m uvicorn app.main:app --port 8000
# 3. Open http://localhost:8000
```

---

## 10. Where things are

```
cv project/
├── HOW_IT_WORKS.md       ← this file
├── README.md             setup, configuration, API, deployment
├── BUILD_LOG.md          record of what was built, decisions and test results
├── demo_photos/          photos for the presentation
├── reference_photos/     144 labelled training photos (earthwork/ foundation/ structure/ finishing/) + sources.csv
├── backend/
│   ├── app/cv/           pipeline.py (steps 1–18), model.py (k-NN), change.py (step 20), train.py, render.py
│   ├── app/services/     workflow (runs the analysis), explain ("how we got the answer"), progress,
│   │                     prediction (forecast), reports (PDFs), stages
│   ├── app/routers/      API endpoints
│   ├── configs/          stages.yaml (stages, weights, phases), reference_features.json (trained features)
│   └── tests/            automated tests
├── frontend/             index.html, css/style.css, js/ (plain HTML + CSS + JavaScript)
└── data/                 uploaded photos, analysis images, database files
```

---

## 11. Glossary

| Term | Meaning |
| --- | --- |
| **HSV** | Colour space: hue (which colour), saturation (how strong), value (how bright) |
| **CLAHE** | Contrast-limited adaptive histogram equalisation: improves contrast tile by tile |
| **Canny / Sobel / Laplacian** | Edge detectors: first-derivative (Sobel, Canny) and second-derivative (Laplacian) |
| **Hough transform** | Finds straight lines by letting edge pixels vote for line positions |
| **ORB / RANSAC / homography** | Keypoint matching; a robust fit of the transform that maps one photo onto the other |
| **LBP** | Local Binary Pattern: a code per pixel describing its neighbourhood (texture) |
| **FFT** | Fast Fourier Transform: the image as a sum of repeating patterns (frequencies) |
| **k-NN** | k-nearest neighbours: classify by the most similar labelled examples |
| **Leave-one-out** | Test each photo with a model built from all the others |
| **Earned Schedule / SPI** | The plan date at which current progress *should* have been reached; SPI = speed vs plan |
| **Lower bound** | A cautious value: progress is at least this much |
