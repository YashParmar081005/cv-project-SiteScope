"""Change detection between two photos of the same site (method orb-ransac-diff/v1).

1. ORB keypoints + descriptors in both photos, brute-force Hamming matching with Lowe's ratio test.
2. RANSAC homography: the geometric transform most matches agree on. Too few inliers, a distorted
   transform or little overlap → the photos are treated as different viewpoints and nothing more is computed.
3. The newer photo is warped onto the older one; CLAHE-normalised, blurred absolute difference;
   Otsu threshold (min 30) and morphological opening/closing give the changed regions.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import render as R
from .pipeline import Step

MIN_GOOD_MATCHES, MIN_INLIERS, MIN_INLIER_RATIO, MIN_OVERLAP = 12, 30, 0.25, 0.3


def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))


def compare(previous: np.ndarray, current: np.ndarray, days_between: int) -> Step:
    """Both images at working size (pipeline.Analysis.image). Returns a pipeline step."""
    ga, gb = _gray(previous), _gray(current)
    orb = cv2.ORB_create(nfeatures=3000)
    kp_a, des_a = orb.detectAndCompute(ga, None)
    kp_b, des_b = orb.detectAndCompute(gb, None)
    metrics = {"days_since_previous": days_between, "keypoints_previous": len(kp_a), "keypoints_current": len(kp_b),
               "good_matches": 0, "inliers": 0, "same_viewpoint": False, "changed_area_share": None}
    step = Step("change", "Change since the previous photo",
                "ORB matching (ratio test 0.75) → cv2.findHomography (RANSAC 5 px) → cv2.warpPerspective → absdiff → Otsu → morphology",
                "If both photos show the same viewpoint, the newer one is aligned to the older one and the changed area "
                "is measured: new structure, removed soil, moved machines.",
                {"ratio_test": 0.75, "ransac_px": 5.0, "min_inliers": MIN_INLIERS}, metrics)
    good = []
    if des_a is not None and des_b is not None and len(kp_a) >= 8 and len(kp_b) >= 8:
        pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_b, des_a, k=2)
        good = [m for m, *rest in pairs if rest and m.distance < 0.75 * rest[0].distance]
    metrics["good_matches"] = len(good)
    if len(good) < MIN_GOOD_MATCHES:
        metrics["reason"] = f"only {len(good)} matching features: different viewpoint or scene"
        step.image = R.grid([("Previous photo", previous), ("This photo", current)])
        return step
    pts_b = np.float32([kp_b[m.queryIdx].pt for m in good])
    pts_a = np.float32([kp_a[m.trainIdx].pt for m in good])
    hom, mask = cv2.findHomography(pts_b, pts_a, cv2.RANSAC, 5.0)
    inliers = int(mask.sum()) if mask is not None else 0
    metrics["inliers"] = inliers
    matches_img = cv2.drawMatches(current, kp_b, previous, kp_a, [m for m, k in zip(good, mask.ravel()) if k][:60] if mask is not None else [],
                                  None, matchColor=(0, 200, 0), flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    h, w = previous.shape[:2]
    reasons = []
    if hom is None:
        reasons.append("no consistent transform")
    else:
        corners = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), hom)
        quad = np.zeros((h, w), np.uint8)
        if cv2.isContourConvex(corners.astype(np.float32)):
            cv2.fillConvexPoly(quad, corners.reshape(-1, 2).astype(np.int32), 1)
        overlap = float(quad.mean())
        det = float(np.linalg.det(hom[:2, :2]))
        if inliers < MIN_INLIERS:
            reasons.append(f"{inliers} inliers (need {MIN_INLIERS})")
        if inliers / len(good) < MIN_INLIER_RATIO:
            reasons.append(f"inlier ratio {inliers / len(good):.2f}")
        if not 0.2 <= abs(det) <= 5 or det <= 0:
            reasons.append("distorted transform")
        if overlap < MIN_OVERLAP:
            reasons.append(f"overlap {overlap:.0%}")
    if reasons:
        metrics["reason"] = "viewpoints differ: " + ", ".join(reasons)
        step.image = R.caption(R.fit_width(matches_img, 640), "Feature matches (green = RANSAC inliers)")
        return step

    warped = cv2.warpPerspective(current, hom, (w, h))
    valid = cv2.erode(cv2.warpPerspective(np.full(current.shape[:2], 255, np.uint8), hom, (w, h)), np.ones((9, 9), np.uint8)) > 0
    diff = cv2.absdiff(cv2.GaussianBlur(ga, (7, 7), 0), cv2.GaussianBlur(_gray(warped), (7, 7), 0))
    diff[~valid] = 0
    otsu, _ = cv2.threshold(diff[valid], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    changed = (diff >= max(30.0, float(otsu))).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    changed = cv2.morphologyEx(cv2.morphologyEx(changed, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel) & valid.astype(np.uint8)
    share = float(changed.sum() / max(1, valid.sum()))
    metrics.update(same_viewpoint=True, changed_area_share=round(share, 4), overlap=round(float(valid.mean()), 3), reason="aligned")
    heat = R.overlay(previous, [(changed, (40, 40, 230))], 0.55)
    heat[~valid] = (heat[~valid] * 0.35).astype(np.uint8)
    step.image = np.vstack([R.caption(R.fit_width(matches_img, 640), "Feature matches (green = RANSAC inliers)"),
                            R.grid([("Newer photo aligned to the older one", warped), ("Changed regions (red)", heat)], tile_width=320)])
    return step
