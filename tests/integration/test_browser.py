"""Real Chromium, no AI: proves captures are deterministic and the pixel engine is trustworthy."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from smartvisionqa.capture import CaptureError, CaptureRequest, PlaywrightCapturer
from smartvisionqa.config import CaptureSettings, DiffSettings, Viewport
from smartvisionqa.diff import compare_images
from smartvisionqa.evaluation.mutations import DEFAULT_MUTATIONS
from smartvisionqa.evaluation.runner import run_evaluation
from smartvisionqa.targets import resolve_target
from tests.integration.conftest import DEMO

pytestmark = pytest.mark.integration


VIEWPORT = Viewport(name="desktop", width=1280, height=800)


@pytest.fixture(scope="module")
def capturer() -> Iterator[PlaywrightCapturer]:
    with PlaywrightCapturer(CaptureSettings(timeout_ms=15_000)) as instance:
        yield instance


def shot(capturer: PlaywrightCapturer, page: str, **kwargs: object) -> bytes:
    target = resolve_target(page, DEMO)
    return capturer.capture(CaptureRequest(target=target, viewport=VIEWPORT, **kwargs))  # type: ignore[arg-type]


def test_captures_are_deterministic(capturer: PlaywrightCapturer) -> None:
    first, second = shot(capturer, "page_v1.html"), shot(capturer, "page_v1.html")
    assert compare_images(first, second, DiffSettings()).raw_changed_pixels == 0


def test_real_regression_is_detected(capturer: PlaywrightCapturer) -> None:
    result = compare_images(
        shot(capturer, "page_v1.html"), shot(capturer, "page_v2.html"), DiffSettings()
    )
    assert result.is_regression(DiffSettings())
    assert result.regions


def test_masks_hide_dynamic_content(capturer: PlaywrightCapturer) -> None:
    script = "() => { document.querySelector('h1').textContent = 'Changed'; }"
    base = shot(capturer, "page_v1.html", mask=("h1",))
    mutated = shot(capturer, "page_v1.html", mask=("h1",), script=script)
    assert compare_images(base, mutated, DiffSettings()).changed_pixels == 0


def test_every_mutation_applies_and_pixel_engine_is_perfect(capturer: PlaywrightCapturer) -> None:
    target = resolve_target("page_v1.html", DEMO)
    report = run_evaluation(target, capturer, None, VIEWPORT, DiffSettings(), DEFAULT_MUTATIONS)
    assert [c.mutation_id for c in report.cases if c.error] == []
    assert report.metrics.detection_recall == 1.0
    assert report.metrics.false_positive_rate == 0.0


def test_url_targets_work(capturer: PlaywrightCapturer, demo_server: str) -> None:
    from_url = shot(capturer, f"{demo_server}/page_v1.html")
    from_file = shot(capturer, "page_v1.html")
    assert compare_images(from_url, from_file, DiffSettings()).changed_pixels == 0


def test_unreachable_url_raises_capture_error(capturer: PlaywrightCapturer) -> None:
    with pytest.raises(CaptureError):
        shot(capturer, "http://127.0.0.1:9/nothing-here")


def test_http_error_pages_are_not_captured_as_healthy(
    capturer: PlaywrightCapturer, demo_server: str
) -> None:
    with pytest.raises(CaptureError, match="404"):
        shot(capturer, f"{demo_server}/does-not-exist.html")


def test_strict_csp_pages_can_still_be_captured(
    capturer: PlaywrightCapturer, tmp_path: Path
) -> None:
    page = tmp_path / "csp.html"
    page.write_text(
        "<html><head><meta http-equiv='Content-Security-Policy' content=\"style-src 'self'\">"
        "</head><body><h1>Strict CSP</h1></body></html>"
    )
    target = resolve_target(str(page), tmp_path)
    assert capturer.capture(CaptureRequest(target=target, viewport=VIEWPORT))
