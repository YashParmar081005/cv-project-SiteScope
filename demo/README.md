# Demo pack — how to show SiteScope to your teacher

Everything here is ready to use. Follow part 1 top to bottom and the whole demo takes about 8 minutes.
Every number below was produced by actually running this app on these photos, so nothing should surprise you.

```
demo/
├── 01_same_site_timeline/   6 photos of ONE building site, Feb → Oct    ← the main demo
└── 02_other_examples/       5 extra photos (a road project + 2 finished buildings)
```

---

## Before you start (2 minutes)

1. MongoDB must be running (on this machine it runs as a Windows service, so it already is).
2. Start the server:
   ```
   cd backend
   .venv\Scripts\python -m uvicorn app.main:app --port 8000
   ```
3. Open <http://localhost:8000> — you get the landing page. Click **Open the app** and sign in.
4. **Delete any old demo project first**, so the numbers below come out exactly right (hover a project card and
   click the bin icon).

---

## Part 1 — the main demo: one site over 8 months

### Step 1. Create the project

Click **+ Add project** and enter exactly this:

| Field | Value |
| --- | --- |
| Project name | `Green Park Tower` |
| Type | **Residential building** |
| Location | anything, e.g. `Vadodara` |
| Start date | `2026-02-02` |
| Planned finish date | `2027-04-30` |

> **Say this:** "A residential building is split into 5 stages, and each stage is a different share of the total
> work: site prep 10%, foundation 15%, frame 35%, envelope 20%, finishing 20%. That is what turns a photo into
> a percentage."

### Step 2. Upload the 6 photos, in order

For each photo: **Add a site photo** → choose the file → type the date → **Analyse photo**.
The date is in the filename.

| # | File | Date to enter | What the computer vision will say | What you confirm | Progress after |
| --- | --- | --- | --- | --- | --- |
| 1 | `2026-02-16_photo-1_site-clearing.jpg` | `2026-02-16` | Earthwork · *low* → **Site preparation 60%** | accept **60%** | **6.0%** |
| 2 | `2026-04-06_photo-2_excavation.jpg` | `2026-04-06` | Earthwork · *medium* → **Site preparation 50%** | change to **100%** | **10.0%** |
| 3 | `2026-05-25_photo-3_foundation-digging.jpg` | `2026-05-25` | Foundation · *low* → **Foundation 50%** | accept **50%** | **17.5%** |
| 4 | `2026-07-13_photo-4_foundation-piling.jpg` | `2026-07-13` | Foundation · *low* → **Foundation 50%** | change to **100%** | **25.0%** |
| 5 | `2026-09-07_photo-5_structure-rebar.jpg` | `2026-09-07` | Structure · *low* → **Structural frame 50%** | change to **40%** | **39.0%** |
| 6 | `2026-10-19_photo-6_structure-formwork.jpg` | `2026-10-19` | **Finishing** · *medium* → **Walls & envelope 100%** | change to **Structural frame · 65%** | **47.8%** |

On each photo page, before you confirm:

- The **"In simple words"** box is the first thing you see: how much is done, how much is left, which stage is
  going on now, and which stages are finished.
- **"Show how the computer looked at this photo"** opens the 18 CV steps — only open this when the teacher asks,
  otherwise it buries the answer.
- Photos 2–6 also get a **change-detection** step: how much of the frame changed since the previous photo.

> **Say this at photo 2:** "The computer suggested 50%, but I was on site and the excavation was finished, so I
> correct it. That is the whole design — the computer measures, the engineer decides."

> **Say this at photo 6 (the important one):** "Here the computer gets it *wrong*. The formwork and scaffolding
> have so many straight lines and rectangles that it looks like a finished facade, so it guesses the finishing
> phase. I correct it to Structural frame 65%. This is exactly why the app never writes a percentage by
> itself — 59% exact accuracy is useful as a suggestion, not as a fact."

### Step 3. The payoff — go back to the project page

After the 6th photo, the project page shows:

| | |
| --- | --- |
| **Progress** | **47.8%** |
| **Estimated completion** | **29 July 2027** |
| **Likely range** | 28 May 2027 – 29 July 2027 |
| **Against the plan** | **90 days late** (planned 30 Apr 2027) |
| **Confidence** | **medium** — the highest this app will ever report |
| **Working speed** | SPI(t) = **0.833**, i.e. 83% of planned speed |
| **Work left** | ≈ 283 days (~9.3 months) |

> **Say this:** "Two independent methods agree here. **Earned Schedule** says: the plan expected 47.8% by 1 May,
> we only got there on 19 October, so we are running at 83% speed and the rest will take proportionally longer.
> The **velocity trend** fits a straight line through the six progress points — r² is 0.99 — and extrapolates to
> 24 June. They agree within 25%, the data is recent and there are 6 points, so the app allows *medium*
> confidence. It is never allowed to say *high*, because it has never been checked against finished real
> projects."

### Step 4. Show the report

Click **Download project report (PDF)**, and on any photo **Download analysis report (PDF)** — every step,
every parameter, every measured number and the full derivation.

---

## Part 2 — the extra photos (3 minutes)

These show the honest limits. Use them if you have time or if the teacher pushes.

### A road project — where it fails, and fails *safely*

Make a second project, type **Road**, and upload the three `road-project_*.jpg` files.

| File | CV says | What the app shows |
| --- | --- | --- |
| `road-project_1_earthwork.jpg` | Structure · *medium* | **No stage suggestion — choose it yourself** |
| `road-project_2_earthwork-loading.jpg` | Structure · *low* | **No stage suggestion** |
| `road-project_3_base-layers.jpg` | Structure · *medium* | **No stage suggestion** |

> **Say this:** "All three are wrong — they are earthwork and base layers, not structure. The reason is
> explainable: grey asphalt and gravel read as *concrete* in the colour step, and concrete is the strongest
> signal for the structure phase. But look at what the app does with a wrong answer: a road project has no
> 'structure' stage at all, so instead of forcing a number it says it has no suggestion and asks me. It fails
> loudly, not silently."

### Two finished buildings — what the last phase looks like

`finishing-example_1_windows-facade.jpg` → Finishing → *Walls & envelope 10%*
`finishing-example_2.jpg` → Finishing → *Walls & envelope 55%*

> **Be honest about these two:** they are part of the 144 labelled reference photos the classifier learns from,
> so the app finds them at distance 0 — it is recognising a photo it has already been taught. They are here to
> *show what the finishing phase looks like*, not as a fair test. Every photo in part 1 and the road photos are
> held out and were never used in training.

---

## Questions your teacher will probably ask

**"Is this AI / machine learning?"**
There is no neural network. The classifier is k-nearest neighbours, which is machine learning in the classical
sense: it stores 144 labelled examples and compares a new one against them. Every step before that is a
textbook OpenCV algorithm.

**"How does it know what is in the photo?"**
It does not recognise objects. It measures 15 properties — how much brown/grey/green there is, how many long
vertical and horizontal lines, how many rectangles and corners, how rough the texture is — and an empty plot
scores very differently from a concrete frame.

**"Why only 59% accurate?"**
Four classes, so random guessing is 25%. It is 91.7% correct within one phase, meaning it is rarely badly
wrong. And it is never used alone — the human confirms every photo.

**"What if I upload a photo of a different corner of the site?"**
Progress cannot go down. The app keeps the most advanced stage you have confirmed and writes a note explaining
that it saw an earlier stage.

**"Could it be fooled?"**
Yes — the road photos prove it. Grey surfaces read as concrete. A photo taken very close to one wall, at night,
or in heavy rain will also measure badly.

**"Where does the completion date come from?"**
Two standard project-management methods, both shown with their numbers: Earned Schedule (Lipke, 2003) and an
ordinary least-squares velocity trend. The app shows both, takes the range between them, and refuses to give a
date when progress is flat ("stalled") or when there is only one data point.

---

## Photo sources and licences

| Folder | Source | Licence | In the training set? |
| --- | --- | --- | --- |
| `01_same_site_timeline/` | Roboflow Universe "Construction Site Safety" | CC BY 4.0 | **No** — held out, genuine predictions |
| `02_other_examples/road-project_*` | Roboflow Universe "Construction Site Safety" | CC BY 4.0 | **No** — held out |
| `02_other_examples/finishing-example_1` | Wikimedia Commons, Fons Heijnsbroek | CC0 | **Yes** — illustration only |
| `02_other_examples/finishing-example_2` | Wikimedia Commons, Nick-D | CC BY-SA 4.0 | **Yes** — illustration only |

The 6 timeline photos are not really one site photographed over 8 months — they are 6 different sites, ordered
by construction phase and given dates, which is the normal way to demonstrate this without waiting a year. Say
so if asked; it does not change anything about how the app works.
