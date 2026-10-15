"""Downscale synthetic stills before a Gemini call. Images are not stored."""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_EDGE = 768


def jpeg_downscale(data: bytes, max_edge: int = MAX_EDGE, quality: int = 70) -> bytes:
    """RGB JPEG, longest side <= max_edge. Returns the original bytes if decoding fails."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            clean = ImageOps.exif_transpose(image).convert("RGB")
            clean.thumbnail((max_edge, max_edge))
            output = io.BytesIO()
            clean.save(output, format="JPEG", quality=quality, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return data
