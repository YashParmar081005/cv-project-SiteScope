"""Classical computer-vision pipeline for a construction-site photo (method classical-cv/v1).

Every step is a textbook CV algorithm implemented with OpenCV/NumPy. Each returns an output image for
the report, the parameters used and the values it measured. The final step turns the measurements
into a feature vector that the phase model (model.py) compares with reference site photos.

 1 resize + colour spaces      7 Otsu + adaptive threshold   13 contours + polygon approx.
 2 histogram + CLAHE           8 morphology                  14 Harris + Shi-Tomasi corners
 3 Gaussian/median/bilateral   9 Sobel gradients             15 ORB keypoints
 4 sky detection               10 Laplacian                  16 LBP texture
 5 HSV colour segmentation     11 Canny edges                17 Fourier transform
 6 K-means colour clustering   12 Hough lines                18 feature vector
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import render as R

METHOD = "classical-cv/v1"
WORK_SIZE = 640
MATERIAL_COLOURS = {  # BGR for the segmentation overlay
    "soil": (40, 90, 160), "vegetation": (60, 170, 60), "concrete": (200, 200, 200),
    "steel_dark": (120, 40, 120), "machinery": (0, 200, 255), "other": (80, 80, 80),
}
FEATURES = ["sky", "soil", "vegetation", "concrete", "steel_dark", "machinery", "edge_density", "vertical_lines",
            "horizontal_lines", "rectangles", "corners", "texture_entropy", "axis_frequency", "vertical_edge_share",
            "orthogonality"]


@dataclass
class Step:
    key: str
    title: str
    algorithm: str
    purpose: str
    params: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    image: np.ndarray | None = None


@dataclass
class Analysis:
    steps: list[Step]
    features: dict[str, float]
    image: np.ndarray  # working-size BGR image


def working_image(image_bgr: np.ndarray) -> np.ndarray:
    """Resize so the longer side is WORK_SIZE pixels (all measurements are made at this size)."""
    h, w = image_bgr.shape[:2]
    scale = WORK_SIZE / max(h, w)
    return cv2.resize(image_bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def _r(v: float, n: int = 3) -> float:
    return round(float(v), n)


def analyze(image_bgr: np.ndarray, *, render: bool = True) -> Analysis:
    """Run the full pipeline. With render=False the step images are skipped (used for training)."""
    steps: list[Step] = []
    show = (lambda f: f()) if render else (lambda f: None)

    # 1 ── resize + colour spaces
    H0, W0 = image_bgr.shape[:2]
    img = working_image(image_bgr)
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    Hh, S, V = (hsv[..., i].astype(np.int32) for i in range(3))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    steps.append(Step(
        "colour_spaces", "Resize & colour spaces", "cv2.resize (INTER_AREA) · cvtColor BGR→GRAY, BGR→HSV",
        "Work at a fixed size so every photo is measured the same way; HSV separates colour (hue) from brightness.",
        {"original": f"{W0}×{H0}", "working": f"{w}×{h}"},
        {"mean_brightness": _r(V.mean() / 255), "mean_saturation": _r(S.mean() / 255)},
        show(lambda: R.grid([("Original (resized)", img), ("Grayscale", gray),
                             ("Hue channel", cv2.applyColorMap((hsv[..., 0].astype(np.float32) * 255 / 180).astype(np.uint8), cv2.COLORMAP_HSV)),
                             ("Saturation channel", hsv[..., 1])]))))

    # 2 ── histogram + CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    steps.append(Step(
        "histogram", "Histogram & contrast enhancement (CLAHE)", "cv2.calcHist · cv2.createCLAHE(clipLimit=2, 8×8 tiles)",
        "The histogram shows how brightness is distributed; CLAHE equalises it locally so details in shadows and bright sky become visible.",
        {"clip_limit": 2.0, "tiles": "8×8"},
        {"contrast_before": _r(gray.std() / 128), "contrast_after": _r(clahe.std() / 128),
         "dark_pixels": _r((gray < 50).mean()), "bright_pixels": _r((gray > 205).mean())},
        show(lambda: R.grid([("Histogram (original)", R.histogram(gray)), ("Histogram (after CLAHE)", R.histogram(clahe, color=(30, 120, 220))),
                             ("Grayscale", gray), ("CLAHE enhanced", clahe)]))))

    # 3 ── noise reduction
    gauss = cv2.GaussianBlur(gray, (5, 5), 0)
    noise = cv2.absdiff(gray, gauss)
    steps.append(Step(
        "filters", "Noise reduction filters", "cv2.GaussianBlur 5×5 · cv2.medianBlur 5 · cv2.bilateralFilter 9/75/75",
        "Smoothing removes sensor noise before edge detection; the bilateral filter smooths while keeping edges sharp.",
        {"gaussian_kernel": "5×5", "median_kernel": 5, "bilateral": "d=9, σcolour=75, σspace=75"},
        {"noise_level": _r(noise.mean() / 255, 4)},
        show(lambda: R.grid([("Gaussian blur", gauss), ("Median blur", cv2.medianBlur(gray, 5)),
                             ("Bilateral filter", cv2.bilateralFilter(img, 9, 75, 75)), ("Removed noise (×4)", np.clip(noise.astype(np.int32) * 4, 0, 255).astype(np.uint8))]))))

    # 4 ── sky detection: colour threshold → connected components touching the top → morphology
    candidate = ((((Hh >= 90) & (Hh <= 135) & (S > 25) & (V > 110)) | ((S < 30) & (V > 190)))).astype(np.uint8)
    _, labels = cv2.connectedComponents(candidate)
    top_labels = set(np.unique(labels[0][candidate[0] > 0])) - {0}
    sky = np.isin(labels, list(top_labels)).astype(np.uint8)
    sky = cv2.morphologyEx(sky, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    site = sky == 0
    site_area = max(1, int(site.sum()))
    steps.append(Step(
        "sky", "Sky detection", "HSV threshold → cv2.connectedComponents (regions touching the top edge) → morphological closing",
        "Sky is removed so that all later measurements describe only the construction site.",
        {"blue_sky": "H 90–135, S>25, V>110", "overcast_sky": "S<30, V>190", "closing_kernel": "7×7"},
        {"sky_share": _r(sky.mean()), "site_share": _r(site.mean())},
        show(lambda: R.overlay(img, [(sky, (230, 160, 40))]))))

    # 5 ── HSV colour segmentation of materials
    def clean(m):
        return cv2.morphologyEx((m & site).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    machinery = clean((Hh >= 15) & (Hh <= 35) & (S > 140) & (V > 140))
    soil = clean((Hh >= 5) & (Hh <= 25) & (S >= 40) & (V >= 40) & (V <= 215)) & ~machinery
    vegetation = clean((Hh >= 33) & (Hh <= 90) & (S > 40) & (V > 40))
    concrete = clean((S < 40) & (V >= 70) & (V <= 230))
    steel_dark = clean(V < 60)
    masks = {"soil": soil, "vegetation": vegetation, "concrete": concrete, "steel_dark": steel_dark, "machinery": machinery}
    covered = np.zeros_like(site)
    for m in masks.values():
        covered |= m
    shares = {k: _r(m.sum() / site_area) for k, m in masks.items()}
    shares["other"] = _r(max(0.0, 1 - covered.sum() / site_area))
    steps.append(Step(
        "materials", "Colour segmentation (HSV thresholds)", "cv2.inRange-style HSV thresholds + morphological opening 3×3",
        "Each pixel of the site is classified by colour: brown soil (earthwork), grey concrete/gravel, green vegetation, "
        "dark steel/shadow, yellow machinery. Their shares describe what the site is made of.",
        {"soil": "H 5–25, S≥40, 40≤V≤215", "concrete": "S<40, 70≤V≤230", "vegetation": "H 33–90, S>40",
         "steel_dark": "V<60", "machinery": "H 15–35, S>140, V>140"},
        shares,
        show(lambda: np.vstack([R.fit_width(R.overlay(img, [(m, MATERIAL_COLOURS[k]) for k, m in masks.items()], 0.65), WORK_SIZE),
                                R.bar_chart([(k, v) for k, v in shares.items()], WORK_SIZE, fmt="{:.0%}", colors=MATERIAL_COLOURS)]))))

    # 6 ── K-means colour clustering
    cv2.setRNGSeed(42)
    pixels = img[site].reshape(-1, 3).astype(np.float32)
    sample = pixels[np.random.default_rng(42).choice(len(pixels), size=min(len(pixels), 20000), replace=False)] if len(pixels) else pixels
    k = 5
    if len(sample) >= k:
        _, _, centres = cv2.kmeans(sample, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 3, cv2.KMEANS_PP_CENTERS)
        flat = img.reshape(-1, 3).astype(np.float32)
        nearest = np.argmin(((flat[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
        quantised = centres[nearest].reshape(img.shape).astype(np.uint8)
        counts = np.bincount(nearest[site.ravel()], minlength=k) / site_area
        order = np.argsort(-counts)
        dominant = [("#%02x%02x%02x" % tuple(int(c) for c in centres[i][::-1]), _r(counts[i])) for i in order]
    else:
        quantised, dominant, order, centres, counts = img, [], [], np.zeros((0, 3)), np.zeros(0)
    steps.append(Step(
        "kmeans", "K-means colour clustering", "cv2.kmeans (k=5, k-means++ init, 3 attempts)",
        "Groups all site pixels into the 5 most representative colours: a compact summary of the scene's materials.",
        {"k": k, "sampled_pixels": len(sample)},
        {"dominant_colours": [c for c, _ in dominant], "colour_shares": [s for _, s in dominant]},
        show(lambda: np.vstack([R.fit_width(quantised, WORK_SIZE),
                                R.palette([centres[i] for i in order], [counts[i] for i in order], WORK_SIZE)]))))

    # 7 ── thresholding
    otsu_t, otsu = cv2.threshold(gauss, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(gauss, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5)
    steps.append(Step(
        "threshold", "Thresholding (Otsu & adaptive)", "cv2.threshold(THRESH_OTSU) · cv2.adaptiveThreshold(Gaussian, 31×31, C=5)",
        "Otsu picks the global brightness threshold that best separates two classes; adaptive thresholding uses a local "
        "threshold per neighbourhood and reveals structure outlines under uneven light.",
        {"adaptive_block": 31, "adaptive_C": 5},
        {"otsu_threshold": int(otsu_t), "otsu_foreground": _r((otsu > 0).mean()), "adaptive_foreground": _r((adaptive > 0).mean())},
        show(lambda: R.grid([(f"Otsu (t = {int(otsu_t)})", otsu), ("Adaptive Gaussian", adaptive)]))))

    # 8 ── morphology
    kernel = np.ones((5, 5), np.uint8)
    opened = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel)
    n_before = cv2.connectedComponents(otsu)[0] - 1
    n_after = cv2.connectedComponents(opened)[0] - 1
    steps.append(Step(
        "morphology", "Morphological operations", "cv2.erode · cv2.dilate · MORPH_OPEN · MORPH_CLOSE (5×5 kernel)",
        "Erosion/dilation shrink and grow shapes; opening removes small specks, closing fills small holes. "
        "Counting connected regions before and after shows how fragmented the scene is.",
        {"kernel": "5×5"},
        {"regions_before": int(n_before), "regions_after_opening": int(n_after)},
        show(lambda: R.grid([("Erosion", cv2.erode(otsu, kernel)), ("Dilation", cv2.dilate(otsu, kernel)),
                             ("Opening", opened), ("Closing", cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel))]))))

    # 9 ── Sobel gradients
    gx = cv2.Sobel(gauss, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gauss, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    ax, ay = float(np.abs(gx)[site].sum()), float(np.abs(gy)[site].sum())
    vertical_share = ax / max(1e-6, ax + ay)
    angle = (np.degrees(np.arctan2(gy, gx)) + 180) % 90  # 0 or 90 = horizontal/vertical edge
    orthogonality = float(mag[site & ((angle < 15) | (angle > 75))].sum() / max(1e-6, mag[site].sum()))
    steps.append(Step(
        "sobel", "Sobel gradients", "cv2.Sobel (3×3) in x and y · cv2.magnitude",
        "Gx responds to vertical edges (columns, walls), Gy to horizontal edges (slabs, floors). Man-made structure "
        "has gradients pointing mostly horizontally or vertically (orthogonality); soil and nature point every way.",
        {"kernel": "3×3", "orthogonal_band": "±15° of 0°/90°"},
        {"mean_gradient": _r(mag[site].mean() / 255), "vertical_edge_share": _r(vertical_share),
         "orthogonality": _r(orthogonality)},
        show(lambda: R.grid([("|Gx| vertical edges", R.normalise(gx)), ("|Gy| horizontal edges", R.normalise(gy)),
                             ("Gradient magnitude", R.normalise(mag))], cols=3, tile_width=213))))

    # 10 ── Laplacian
    lap = cv2.Laplacian(gauss, cv2.CV_32F, ksize=3)
    lap_var = float(lap[site].var())
    steps.append(Step(
        "laplacian", "Laplacian (second derivative)", "cv2.Laplacian (3×3)",
        "Highlights rapid intensity changes; its variance measures sharpness and fine texture (rough soil vs smooth surfaces).",
        {"kernel": "3×3"}, {"laplacian_variance": _r(lap_var, 1)},
        show(lambda: R.normalise(lap))))

    # 11 ── Canny
    med = float(np.median(gauss))
    low, high = int(max(0, 0.66 * med)), int(min(255, 1.33 * med))
    edges = cv2.Canny(gauss, low, high)
    edges[~site] = 0
    edge_density = float((edges > 0).sum() / site_area)
    steps.append(Step(
        "canny", "Canny edge detector", "cv2.Canny with automatic thresholds (0.66 × and 1.33 × median brightness)",
        "Finds thin, connected edges using gradient direction, non-maximum suppression and hysteresis. Edge density "
        "tells how much detail/structure the site contains.",
        {"low_threshold": low, "high_threshold": high},
        {"edge_density": _r(edge_density, 4)},
        show(lambda: edges)))

    # 12 ── Hough lines
    diag = (h * h + w * w) ** 0.5
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60, minLineLength=int(0.08 * diag), maxLineGap=6)
    lines = lines.reshape(-1, 4) if lines is not None else np.zeros((0, 4), np.int32)
    vert_len = horiz_len = total_len = 0.0
    n_vert = n_horiz = 0
    hough_img = img.copy() if render else None
    for x0, y0, x1, y1 in lines:
        length = float(np.hypot(x1 - x0, y1 - y0))
        angle = abs(np.degrees(np.arctan2(y1 - y0, x1 - x0))) % 180
        total_len += length
        if abs(angle - 90) < 12:
            vert_len, n_vert, colour = vert_len + length, n_vert + 1, (60, 200, 60)
        elif angle < 12 or angle > 168:
            horiz_len, n_horiz, colour = horiz_len + length, n_horiz + 1, (30, 140, 255)
        else:
            colour = (60, 60, 230)
        if render:
            cv2.line(hough_img, (int(x0), int(y0)), (int(x1), int(y1)), colour, 2, cv2.LINE_AA)
    vertical_lines = min(1.0, vert_len / diag / 10)
    horizontal_lines = min(1.0, horiz_len / diag / 10)
    steps.append(Step(
        "hough", "Hough line transform", "cv2.HoughLinesP (ρ=1 px, θ=1°, votes=60, min length 8 % of diagonal, gap 6)",
        "Detects long straight lines. Earthwork scenes have few; concrete frames, formwork and facades have many "
        "vertical (green) and horizontal (orange) lines.",
        {"votes": 60, "min_length_px": int(0.08 * diag), "max_gap_px": 6},
        {"lines": int(len(lines)), "vertical": n_vert, "horizontal": n_horiz,
         "vertical_density": _r(vertical_lines), "horizontal_density": _r(horizontal_lines),
         "straightness": _r(total_len / max(1, (edges > 0).sum()))},
        show(lambda: hough_img)))

    # 13 ── contours + polygon approximation
    closed = cv2.morphologyEx(cv2.dilate(edges, np.ones((3, 3), np.uint8)), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    min_area = 0.0015 * h * w
    big = [c for c in contours if cv2.contourArea(c) > min_area]
    rects = []
    for c in big:
        approx = cv2.approxPolyDP(c, 0.03 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            rects.append(approx)
    rect_area = sum(cv2.contourArea(r) for r in rects) / (h * w)
    contour_img = None
    if render:
        contour_img = img.copy()
        cv2.drawContours(contour_img, big, -1, (180, 180, 180), 1)
        cv2.drawContours(contour_img, rects, -1, (40, 200, 40), 2)
    steps.append(Step(
        "contours", "Contours & polygon approximation", "cv2.findContours · cv2.approxPolyDP (ε = 3 % of perimeter) · cv2.isContourConvex",
        "Closed outlines are simplified to polygons; convex 4-sided ones (green) are rectangular elements such as "
        "window openings, panels, slabs and formwork boards.",
        {"min_area_px": int(min_area), "epsilon": "3 % of perimeter"},
        {"contours": len(big), "rectangles": len(rects), "rectangle_area_share": _r(rect_area)},
        show(lambda: contour_img)))

    # 14 ── corners
    harris = cv2.cornerHarris(np.float32(gauss), 2, 3, 0.04)
    harris_count = int((harris > 0.01 * harris.max()).sum()) if harris.max() > 0 else 0
    shi = cv2.goodFeaturesToTrack(gauss, maxCorners=5000, qualityLevel=0.01, minDistance=6, mask=site.astype(np.uint8))
    shi = shi.reshape(-1, 2) if shi is not None else np.zeros((0, 2))
    corner_density = min(1.0, len(shi) / 4000)
    corner_img = None
    if render:
        corner_img = img.copy()
        for x, y in shi:
            cv2.circle(corner_img, (int(x), int(y)), 3, (0, 0, 255), -1)
    steps.append(Step(
        "corners", "Corner detection (Harris & Shi-Tomasi)", "cv2.cornerHarris (block 2, k=0.04) · cv2.goodFeaturesToTrack (up to 5000, quality 0.01, 6 px apart)",
        "Corners appear where edges meet: many corners mean man-made structure (beams, openings, scaffolding joints).",
        {"harris_block": 2, "harris_k": 0.04, "max_corners": 5000},
        {"harris_corners": harris_count, "shi_tomasi_corners": int(len(shi)), "corner_density": _r(corner_density)},
        show(lambda: R.grid([("Harris response", cv2.applyColorMap(R.normalise(cv2.dilate(harris, None)), cv2.COLORMAP_JET)),
                             ("Shi-Tomasi corners", corner_img)]))))

    # 15 ── ORB keypoints
    orb = cv2.ORB_create(nfeatures=1000)
    keypoints = orb.detect(gray, site.astype(np.uint8))
    steps.append(Step(
        "orb", "ORB keypoints & descriptors", "cv2.ORB_create(1000): FAST corners + oriented BRIEF descriptors",
        "Distinctive, rotation-invariant points. They are used to match this photo with the previous one (change detection).",
        {"max_keypoints": 1000}, {"keypoints": len(keypoints)},
        show(lambda: cv2.drawKeypoints(img, keypoints, None, (0, 220, 0), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS))))

    # 16 ── LBP texture
    c = gray[1:-1, 1:-1].astype(np.int16)
    lbp = np.zeros_like(c, dtype=np.uint8)
    for bit, (dy, dx) in enumerate([(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]):
        neighbour = gray[1 + dy:h - 1 + dy, 1 + dx:w - 1 + dx].astype(np.int16)
        lbp |= ((neighbour >= c).astype(np.uint8) << bit)
    hist = np.bincount(lbp[site[1:-1, 1:-1]].ravel(), minlength=256).astype(np.float64)
    p = hist / max(1.0, hist.sum())
    entropy = float(-(p[p > 0] * np.log2(p[p > 0])).sum() / 8)
    steps.append(Step(
        "lbp", "Local Binary Patterns (texture)", "8-neighbour LBP computed with NumPy · histogram entropy",
        "Each pixel is coded by which neighbours are brighter. Varied codes (high entropy) = rough, busy texture such "
        "as soil, rubble or rebar; low entropy = smooth plaster, concrete or sky.",
        {"neighbours": 8, "radius": 1}, {"texture_entropy": _r(entropy)},
        show(lambda: R.grid([("LBP image", lbp), ("LBP code histogram", R.histogram(lbp[site[1:-1, 1:-1]].reshape(-1, 1)))]))))

    # 17 ── Fourier transform
    spectrum = np.fft.fftshift(np.fft.fft2(gray.astype(np.float32) - gray.mean()))
    power = np.abs(spectrum) ** 2
    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    ring = ((yy - cy) ** 2 + (xx - cx) ** 2) > 16
    axes = ((np.abs(yy - cy) <= 1) | (np.abs(xx - cx) <= 1)) & ring
    axis_share = float(power[axes].sum() / max(1e-9, power[ring].sum()))
    steps.append(Step(
        "fft", "Fourier transform (frequency domain)", "np.fft.fft2 + fftshift · log magnitude spectrum",
        "Repeated horizontal/vertical patterns (floors, windows, scaffolding) concentrate energy on the spectrum's axes; "
        "irregular natural scenes spread it out.",
        {"excluded_radius_px": 4}, {"axis_energy_share": _r(axis_share, 4)},
        show(lambda: cv2.applyColorMap(R.normalise(np.log1p(np.abs(spectrum))), cv2.COLORMAP_INFERNO))))

    # 18 ── feature vector
    features = {
        "sky": _r(sky.mean()), "soil": shares["soil"], "vegetation": shares["vegetation"], "concrete": shares["concrete"],
        "steel_dark": shares["steel_dark"], "machinery": shares["machinery"], "edge_density": _r(min(1.0, edge_density * 5)),
        "vertical_lines": _r(vertical_lines), "horizontal_lines": _r(horizontal_lines),
        "rectangles": _r(min(1.0, len(rects) / 20)), "corners": _r(corner_density), "texture_entropy": _r(entropy),
        "axis_frequency": _r(axis_share), "vertical_edge_share": _r(vertical_share), "orthogonality": _r(orthogonality),
    }
    steps.append(Step(
        "features", "Feature vector", "Selected measurements from steps 4–17, each scaled to 0–1",
        "These 15 numbers describe the photo. They are compared with the same numbers measured on reference photos of "
        "each construction phase.",
        {"length": len(FEATURES)}, features,
        show(lambda: R.bar_chart([(k, features[k]) for k in FEATURES], WORK_SIZE))))
    for step in steps:  # every step image as 3-channel BGR for the report
        if step.image is not None:
            step.image = R.to_bgr(step.image)
    return Analysis(steps, features, img)
