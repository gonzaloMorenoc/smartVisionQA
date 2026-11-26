"""Deterministic pixel diff: the source of truth for pass/fail decisions.

The vision model never decides whether something changed; it only explains regions this
module has already proven to be different.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from smartvisionqa.config import DiffSettings
from smartvisionqa.imaging import load_rgb, pad_to, to_png

_MAX_CHANNEL = 255.0
_HIGHLIGHT = (255, 0, 0)
_REGION_OUTLINE = (255, 140, 0)
_FADE = 0.25


@dataclass(frozen=True)
class Region:
    """Axis-aligned bounding box in page pixels."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError(f"Invalid region geometry: {self}")

    @property
    def area(self) -> int:
        return self.width * self.height

    def padded(self, pad: int, max_width: int, max_height: int) -> Region:
        x0, y0 = max(0, self.x - pad), max(0, self.y - pad)
        x1 = min(max_width, self.x + self.width + pad)
        y1 = min(max_height, self.y + self.height + pad)
        return Region(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class DiffResult:
    width: int
    height: int
    raw_changed_pixels: int
    changed_pixels: int
    regions: tuple[Region, ...]
    truncated_regions: int
    size_mismatch: bool
    mask: NDArray[np.bool_] = field(repr=False, compare=False)

    @property
    def total_pixels(self) -> int:
        return self.width * self.height

    @property
    def diff_ratio(self) -> float:
        return self.changed_pixels / self.total_pixels if self.total_pixels else 0.0

    def is_regression(self, settings: DiffSettings) -> bool:
        return self.changed_pixels > 0 and self.diff_ratio > settings.max_diff_ratio

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "changed_pixels": self.changed_pixels,
            "raw_changed_pixels": self.raw_changed_pixels,
            "diff_ratio": self.diff_ratio,
            "size_mismatch": self.size_mismatch,
            "regions": [region.to_dict() for region in self.regions],
            "truncated_regions": self.truncated_regions,
        }


def compare_images(before: bytes, after: bytes, settings: DiffSettings) -> DiffResult:
    """Compare two screenshots and cluster significant changes into regions."""
    img_before, img_after = load_rgb(before), load_rgb(after)
    width = max(img_before.width, img_after.width)
    height = max(img_before.height, img_after.height)
    mask = _changed_mask(img_before, img_after, width, height, settings.pixel_threshold)
    clusters = _clusters(mask, settings.cell_size)
    significant = [c for c in clusters if c[1] >= settings.min_region_area]
    significant.sort(key=lambda cluster: cluster[0].area, reverse=True)
    kept = significant[: settings.max_regions]
    return DiffResult(
        width=width,
        height=height,
        raw_changed_pixels=int(mask.sum()),
        changed_pixels=sum(count for _, count in significant),
        regions=tuple(region for region, _ in kept),
        truncated_regions=len(significant) - len(kept),
        size_mismatch=img_before.size != img_after.size,
        mask=mask,
    )


def _changed_mask(
    before: Image.Image, after: Image.Image, width: int, height: int, threshold: float
) -> NDArray[np.bool_]:
    a = np.asarray(pad_to(before, width, height), dtype=np.int16)
    b = np.asarray(pad_to(after, width, height), dtype=np.int16)
    distance = np.abs(a - b).max(axis=2) / _MAX_CHANNEL
    mask: NDArray[np.bool_] = distance > threshold
    for image in (before, after):
        mask[image.height :, :] = True
        mask[:, image.width :] = True
    return mask


def _clusters(mask: NDArray[np.bool_], cell: int) -> list[tuple[Region, int]]:
    """Group changed pixels into regions; clusters separated by <= 2 empty cells merge."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return []
    height, width = mask.shape
    rows, cols = -(-height // cell), -(-width // cell)
    cells = np.zeros((rows, cols), dtype=bool)
    cells[ys // cell, xs // cell] = True
    labels = _label(_dilate(cells))
    pixel_labels = labels[ys // cell, xs // cell]
    order = np.argsort(pixel_labels, kind="stable")
    pixel_labels, ys, xs = pixel_labels[order], ys[order], xs[order]
    _, starts, counts = np.unique(pixel_labels, return_index=True, return_counts=True)
    x_min, x_max = np.minimum.reduceat(xs, starts), np.maximum.reduceat(xs, starts)
    y_min, y_max = np.minimum.reduceat(ys, starts), np.maximum.reduceat(ys, starts)
    return [
        (
            Region(
                x=int(x_min[i]),
                y=int(y_min[i]),
                width=int(x_max[i] - x_min[i] + 1),
                height=int(y_max[i] - y_min[i] + 1),
            ),
            int(counts[i]),
        )
        for i in range(len(starts))
    ]


def _dilate(cells: NDArray[np.bool_]) -> NDArray[np.bool_]:
    padded = np.pad(cells, 1)
    out = np.zeros_like(cells)
    rows, cols = cells.shape
    for dy in range(3):
        for dx in range(3):
            out |= padded[dy : dy + rows, dx : dx + cols]
    return out


def _label(grid: NDArray[np.bool_]) -> NDArray[np.int32]:
    """8-connected component labelling (BFS). Background stays 0."""
    labels = np.zeros(grid.shape, dtype=np.int32)
    rows, cols = grid.shape
    current = 0
    for start_r, start_c in zip(*np.nonzero(grid), strict=True):
        if labels[start_r, start_c]:
            continue
        current += 1
        labels[start_r, start_c] = current
        queue: deque[tuple[int, int]] = deque([(int(start_r), int(start_c))])
        while queue:
            r, c = queue.popleft()
            for nr in range(max(0, r - 1), min(rows, r + 2)):
                for nc in range(max(0, c - 1), min(cols, c + 2)):
                    if grid[nr, nc] and not labels[nr, nc]:
                        labels[nr, nc] = current
                        queue.append((nr, nc))
    return labels


def render_diff_image(after: bytes, result: DiffResult) -> bytes:
    """Faded 'after' image with changed pixels in red and regions outlined."""
    base = pad_to(load_rgb(after), result.width, result.height).convert("L").convert("RGB")
    faded = Image.blend(Image.new("RGB", base.size, (255, 255, 255)), base, _FADE)
    pixels = np.asarray(faded).copy()
    pixels[result.mask] = _HIGHLIGHT
    overlay = Image.fromarray(pixels)
    draw = ImageDraw.Draw(overlay)
    for region in result.regions:
        box = region.padded(2, result.width, result.height)
        draw.rectangle(
            [box.x, box.y, box.x + box.width - 1, box.y + box.height - 1],
            outline=_REGION_OUTLINE,
            width=2,
        )
    return to_png(overlay)
