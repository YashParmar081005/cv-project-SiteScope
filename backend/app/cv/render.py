"""Small OpenCV drawing helpers used to visualise each pipeline step (no plotting library needed)."""
from __future__ import annotations

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX
INK = (40, 40, 40)
GRID = (225, 225, 225)


def to_bgr(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img


def normalise(img: np.ndarray) -> np.ndarray:
    """Stretch any single-channel array to 0–255 uint8 for display."""
    img = np.abs(img.astype(np.float32))
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def fit_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)


def crop_to(img: np.ndarray, width: int, height: int) -> np.ndarray:
    """Centre-crop to the target aspect ratio, then resize (uniform thumbnails)."""
    h, w = img.shape[:2]
    scale = max(width / w, height / h)
    cw, ch = round(width / scale), round(height / scale)
    x, y = (w - cw) // 2, (h - ch) // 2
    return cv2.resize(img[y:y + ch, x:x + cw], (width, height), interpolation=cv2.INTER_AREA)


def caption(img: np.ndarray, text: str) -> np.ndarray:
    """Add a white caption strip above an image."""
    img = to_bgr(img)
    strip = np.full((26, img.shape[1], 3), 255, np.uint8)
    scale = min(0.5, 0.5 * (img.shape[1] - 10) / max(1, cv2.getTextSize(text, FONT, 0.5, 1)[0][0]))
    cv2.putText(strip, text, (5, 18), FONT, scale, INK, 1, cv2.LINE_AA)
    return np.vstack([strip, img])


def grid(panels: list[tuple[str, np.ndarray]], cols: int = 2, tile_width: int = 320) -> np.ndarray:
    """Captioned tiles in a grid (all tiles resized to the same width)."""
    tiles = [caption(fit_width(to_bgr(p), tile_width), t) for t, p in panels]
    height = max(t.shape[0] for t in tiles)
    tiles = [np.vstack([t, np.full((height - t.shape[0], t.shape[1], 3), 255, np.uint8)]) for t in tiles]
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    return np.vstack(rows)


def histogram(gray: np.ndarray, width: int = 320, height: int = 180, color=(60, 60, 60)) -> np.ndarray:
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    hist = hist / max(1.0, hist.max())
    img = np.full((height, width, 3), 255, np.uint8)
    for x in range(0, width, width // 4):
        cv2.line(img, (x, 0), (x, height), GRID, 1)
    pts = np.array([[int(i * (width - 1) / 255), int(height - 5 - v * (height - 15))] for i, v in enumerate(hist)], np.int32)
    cv2.polylines(img, [pts], False, color, 2, cv2.LINE_AA)
    return img


def bar_chart(items: list[tuple[str, float]], width: int = 640, highlight: str | None = None, fmt: str = "{:.2f}",
              colors: dict | None = None) -> np.ndarray:
    """Horizontal bar chart: one row per (label, value)."""
    row = 30
    label_w = 12 + max(cv2.getTextSize(label, FONT, 0.5, 1)[0][0] for label, _ in items)
    img = np.full((row * len(items) + 10, width, 3), 255, np.uint8)
    vmax = max([abs(v) for _, v in items] + [1e-9])
    for i, (label, value) in enumerate(items):
        y = 8 + i * row
        colour = (colors or {}).get(label, (30, 120, 220) if label == highlight else (150, 150, 150))
        cv2.putText(img, label, (6, y + 17), FONT, 0.5, INK, 1, cv2.LINE_AA)
        bar = int((width - label_w - 70) * abs(value) / vmax)
        cv2.rectangle(img, (label_w, y + 4), (label_w + bar, y + row - 6), colour, -1)
        cv2.putText(img, fmt.format(value), (label_w + bar + 6, y + 17), FONT, 0.5, INK, 1, cv2.LINE_AA)
    return img


def palette(colors_bgr: list[tuple[int, int, int]], shares: list[float], width: int = 640, height: int = 60) -> np.ndarray:
    img = np.full((height, width, 3), 255, np.uint8)
    x = 0
    for colour, share in zip(colors_bgr, shares):
        w = int(round(share * width))
        cv2.rectangle(img, (x, 0), (x + w, height - 22), tuple(int(c) for c in colour), -1)
        cv2.putText(img, f"{share:.0%}", (x + 4, height - 6), FONT, 0.45, INK, 1, cv2.LINE_AA)
        x += w
    return img


def overlay(base: np.ndarray, masks: list[tuple[np.ndarray, tuple[int, int, int]]], alpha: float = 0.55) -> np.ndarray:
    out = base.copy()
    for mask, colour in masks:
        tint = np.zeros_like(base)
        tint[:] = colour
        m = mask.astype(bool)
        out[m] = cv2.addWeighted(base, 1 - alpha, tint, alpha, 0)[m]
    return out
