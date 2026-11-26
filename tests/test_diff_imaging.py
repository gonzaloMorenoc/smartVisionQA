from __future__ import annotations

import io

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from smartvisionqa.config import DiffSettings
from smartvisionqa.diff import Region, compare_images, render_diff_image
from smartvisionqa.imaging import ImageError, crop_pair, load_rgb
from tests.conftest import make_png

RED = (255, 0, 0)
BLUE = (0, 0, 255)


class TestCompareImages:
    def test_identical_images_have_no_regions(self) -> None:
        img = make_png(rects=[(10, 10, 20, 20, RED)])
        result = compare_images(img, img, DiffSettings())
        assert result.changed_pixels == 0
        assert result.regions == ()
        assert result.diff_ratio == 0.0
        assert result.is_regression(DiffSettings()) is False

    def test_single_change_produces_one_tight_region(self) -> None:
        before = make_png()
        after = make_png(rects=[(40, 30, 20, 10, RED)])
        result = compare_images(before, after, DiffSettings(cell_size=1))
        assert result.changed_pixels == 200
        assert result.regions == (Region(x=40, y=30, width=20, height=10),)
        assert result.is_regression(DiffSettings()) is True

    def test_far_apart_changes_are_separate_regions_sorted_by_area(self) -> None:
        before = make_png(width=300, height=200)
        after = make_png(
            width=300, height=200, rects=[(5, 5, 10, 10, RED), (200, 120, 40, 40, BLUE)]
        )
        result = compare_images(before, after, DiffSettings())
        assert len(result.regions) == 2
        assert result.regions[0].area >= result.regions[1].area
        big = result.regions[0]
        assert big.x <= 200 and big.y <= 120
        assert big.x + big.width >= 240 and big.y + big.height >= 160

    def test_nearby_changes_are_merged(self) -> None:
        before = make_png()
        after = make_png(rects=[(10, 10, 10, 10, RED), (24, 10, 10, 10, RED)])
        result = compare_images(before, after, DiffSettings(cell_size=8))
        assert len(result.regions) == 1

    def test_tiny_noise_below_min_area_is_ignored(self) -> None:
        before = make_png()
        after = make_png(rects=[(50, 50, 2, 2, RED)])
        result = compare_images(before, after, DiffSettings(min_region_area=16))
        assert result.regions == ()
        assert result.diff_ratio == 0.0
        assert result.raw_changed_pixels == 4

    def test_subtle_color_shift_below_threshold_is_ignored(self) -> None:
        before = make_png(color=(200, 200, 200))
        after = make_png(color=(205, 205, 205))
        assert compare_images(before, after, DiffSettings(pixel_threshold=0.1)).regions == ()
        assert compare_images(before, after, DiffSettings(pixel_threshold=0.01)).regions != ()

    def test_size_mismatch_counts_extra_area_as_changed(self) -> None:
        before = make_png(width=100, height=100)
        after = make_png(width=100, height=150)
        result = compare_images(before, after, DiffSettings())
        assert result.size_mismatch is True
        assert (result.width, result.height) == (100, 150)
        assert result.changed_pixels == 100 * 50
        assert result.regions[0].y == 100

    def test_max_regions_caps_and_flags_truncation(self) -> None:
        rects = [(i * 40, 0, 10, 10, RED) for i in range(8)]
        before = make_png(width=320, height=20)
        after = make_png(width=320, height=20, rects=rects)
        result = compare_images(before, after, DiffSettings(max_regions=3))
        assert len(result.regions) == 3
        assert result.truncated_regions == 5
        assert result.changed_pixels == 800

    def test_threshold_ratio_allows_small_changes(self) -> None:
        before = make_png(width=100, height=100)
        after = make_png(width=100, height=100, rects=[(0, 0, 10, 10, RED)])
        result = compare_images(before, after, DiffSettings())
        assert result.diff_ratio == pytest.approx(0.01)
        assert result.is_regression(DiffSettings(max_diff_ratio=0.02)) is False
        assert result.is_regression(DiffSettings(max_diff_ratio=0.005)) is True

    def test_rgba_input_is_composited_on_white(self) -> None:
        rgba = make_png(mode="RGBA")
        rgb = make_png()
        assert compare_images(rgba, rgb, DiffSettings()).changed_pixels == 0

    @settings(max_examples=25, deadline=None)
    @given(
        x=st.integers(0, 50),
        y=st.integers(0, 40),
        w=st.integers(4, 40),
        h=st.integers(4, 40),
    )
    def test_property_region_always_covers_change(self, x: int, y: int, w: int, h: int) -> None:
        before = make_png(width=100, height=90)
        after = make_png(width=100, height=90, rects=[(x, y, w, h, RED)])
        result = compare_images(before, after, DiffSettings())
        assert len(result.regions) == 1
        region = result.regions[0]
        right, bottom = min(x + w, 100), min(y + h, 90)
        assert region.x <= x and region.y <= y
        assert region.x + region.width >= right and region.y + region.height >= bottom


class TestRegion:
    def test_padded_is_clamped_to_bounds(self) -> None:
        assert Region(x=5, y=5, width=10, height=10).padded(20, 30, 30) == Region(
            x=0, y=0, width=30, height=30
        )

    def test_region_rejects_negative_geometry(self) -> None:
        with pytest.raises(ValueError, match="Invalid region"):
            Region(x=-1, y=0, width=1, height=1)


class TestRenderDiffImage:
    def test_renders_png_of_combined_size(self) -> None:
        before = make_png(width=100, height=100)
        after = make_png(width=100, height=120, rects=[(10, 10, 20, 20, RED)])
        result = compare_images(before, after, DiffSettings())
        image = Image.open(io.BytesIO(render_diff_image(after, result)))
        assert image.size == (100, 120)
        assert image.getpixel((15, 15))[0] > 200  # changed pixel highlighted in red


class TestImaging:
    def test_load_rgb_rejects_non_images(self) -> None:
        with pytest.raises(ImageError):
            load_rgb(b"not a png")

    def test_load_rgb_rejects_decompression_bombs(self) -> None:
        with pytest.raises(ImageError, match="too large"):
            load_rgb(make_png(width=10, height=10), max_pixels=50)

    def test_crop_pair_returns_same_sized_crops_with_padding(self) -> None:
        before = make_png(width=200, height=200)
        after = make_png(width=200, height=250)
        crop_before, crop_after = crop_pair(
            before, after, Region(x=50, y=50, width=10, height=10), pad=20, max_side=512
        )
        a = Image.open(io.BytesIO(crop_before))
        b = Image.open(io.BytesIO(crop_after))
        assert a.size == b.size
        assert a.size[0] >= 50

    def test_crop_pair_downscales_huge_regions(self) -> None:
        before = make_png(width=2000, height=600)
        crop_before, _ = crop_pair(
            before, before, Region(x=0, y=0, width=2000, height=600), pad=0, max_side=500
        )
        assert max(Image.open(io.BytesIO(crop_before)).size) == 500
