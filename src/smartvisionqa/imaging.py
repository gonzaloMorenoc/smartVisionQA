"""Small, safe image helpers built on Pillow."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError

if TYPE_CHECKING:
    from smartvisionqa.diff import Region

DEFAULT_MAX_PIXELS = 120_000_000  # ~ 1920 x 62 500: generous for full-page captures
WHITE = (255, 255, 255)


class ImageError(ValueError):
    """Raised when bytes are not a usable image."""


def load_rgb(data: bytes, max_pixels: int = DEFAULT_MAX_PIXELS) -> Image.Image:
    """Decode PNG/JPEG bytes into RGB, compositing transparency on white."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > max_pixels:
                raise ImageError(f"Image too large: {width}x{height} exceeds {max_pixels} pixels")
            probe.load()
            image: Image.Image = probe.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError(f"Cannot decode image: {exc}") from exc
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, WHITE)
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    converted: Image.Image = image.convert("RGB")
    return converted


def pad_to(image: Image.Image, width: int, height: int) -> Image.Image:
    """Return a copy of ``image`` on a white canvas of the given size (top-left aligned)."""
    if image.size == (width, height):
        return image.copy()
    canvas = Image.new("RGB", (width, height), WHITE)
    canvas.paste(image, (0, 0))
    return canvas


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def crop_pair(
    before: bytes, after: bytes, region: Region, pad: int, max_side: int
) -> tuple[bytes, bytes]:
    """Crop the same (padded) region from both images, downscaled to ``max_side``."""
    img_before, img_after = load_rgb(before), load_rgb(after)
    width = max(img_before.width, img_after.width)
    height = max(img_before.height, img_after.height)
    box = region.padded(pad, width, height)
    crops = []
    for image in (pad_to(img_before, width, height), pad_to(img_after, width, height)):
        crop = image.crop((box.x, box.y, box.x + box.width, box.y + box.height))
        crops.append(to_png(_fit(crop, max_side)))
    return crops[0], crops[1]


def _fit(image: Image.Image, max_side: int) -> Image.Image:
    longest = max(image.size)
    if longest <= max_side:
        return image
    scale = max_side / longest
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)
