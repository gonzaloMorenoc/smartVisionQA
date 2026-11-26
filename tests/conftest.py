"""Shared test helpers: tiny synthetic PNGs so unit tests never need a browser."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable

import pytest
from PIL import Image, ImageDraw

Rect = tuple[int, int, int, int, tuple[int, int, int]]


def make_png(
    width: int = 120,
    height: int = 90,
    color: tuple[int, int, int] = (255, 255, 255),
    rects: Iterable[Rect] = (),
    mode: str = "RGB",
) -> bytes:
    """Build a PNG with a solid background and optional filled rectangles (x, y, w, h, rgb)."""
    image = Image.new(mode, (width, height), color if mode == "RGB" else (*color, 255))
    draw = ImageDraw.Draw(image)
    for x, y, w, h, fill in rects:
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=fill)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def png() -> Callable[..., bytes]:
    return make_png
