"""Upload validation and decoding helpers."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "BMP": "image/bmp"}
MIN_SIDE = 32
MAX_PIXELS = 60_000_000  # guards against decompression bombs

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    """Raised when bytes are not a usable image."""


@dataclass
class ImageInfo:
    width: int
    height: int
    format: str
    content_type: str


def inspect_image(data: bytes) -> ImageInfo:
    """Check that `data` decodes as an allowed image format; return its EXIF-corrected size."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = ImageOps.exif_transpose(img).size
    except Image.DecompressionBombError as exc:
        raise InvalidImage(f"image exceeds {MAX_PIXELS:,} pixels") from exc
    except Exception as exc:  # PIL raises many exception types for corrupt data
        raise InvalidImage(f"cannot decode image: {exc.__class__.__name__}") from exc
    if fmt not in ALLOWED_FORMATS:
        raise InvalidImage(f"unsupported format {fmt!r}; allowed: {', '.join(ALLOWED_FORMATS)}")
    if min(width, height) < MIN_SIDE:
        raise InvalidImage(f"image too small ({width}x{height}); minimum side is {MIN_SIDE}px")
    return ImageInfo(width, height, fmt, ALLOWED_FORMATS[fmt])


def load_rgb(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
