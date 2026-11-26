"""Deterministic screenshots with Playwright (one browser, one context per capture)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

from smartvisionqa.config import CaptureSettings, Viewport
from smartvisionqa.targets import Target

logger = logging.getLogger(__name__)

_FREEZE_CSS = """
*, *::before, *::after {
  animation-duration: 0s !important; animation-delay: 0s !important;
  transition-duration: 0s !important; transition-delay: 0s !important;
  caret-color: transparent !important; scroll-behavior: auto !important;
}
"""


class CaptureError(RuntimeError):
    """Raised when a page cannot be captured."""


_HTTP_ERROR = 400


def _ensure_healthy(target: Target, response: Any) -> None:
    """Never baseline or compare an error page: 4xx/5xx (or no response for a URL) fails."""
    if response is None:
        if target.kind == "url":
            raise CaptureError(f"No HTTP response for {target.label}")
        return
    if response.status >= _HTTP_ERROR:
        raise CaptureError(f"{target.label} answered HTTP {response.status}")


@dataclass(frozen=True)
class CaptureRequest:
    target: Target
    viewport: Viewport
    mask: tuple[str, ...] = ()
    script: str | None = None


class Capturer(Protocol):
    def capture(self, request: CaptureRequest) -> bytes: ...


class PlaywrightCapturer:
    """Context manager that keeps a single headless Chromium alive for a whole run."""

    def __init__(self, settings: CaptureSettings) -> None:
        self._settings = settings
        self._playwright: Any = None
        self._browser: Any = None

    def __enter__(self) -> PlaywrightCapturer:
        from playwright.sync_api import Error, sync_playwright  # noqa: PLC0415

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        except Error as exc:
            self.close()
            raise CaptureError(
                f"Cannot start Chromium ({exc}). Run: python -m playwright install chromium"
            ) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def capture(self, request: CaptureRequest) -> bytes:
        """Capture one page. Every browser failure becomes a :class:`CaptureError`."""
        from playwright.sync_api import Error  # noqa: PLC0415

        if self._browser is None:
            raise CaptureError("PlaywrightCapturer must be used as a context manager")
        context = None
        try:
            context = self._new_context(request.viewport)
            return self._render(context.new_page(), request)
        except Error as exc:
            raise CaptureError(f"Capture of {request.target.label} failed: {exc}") from exc
        finally:
            if context is not None:
                _close_quietly(context, request.target.label)

    def _new_context(self, viewport: Viewport) -> Any:
        return self._browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            device_scale_factor=viewport.device_scale_factor,
            reduced_motion="reduce",
            color_scheme="light",
            locale="en-US",
            timezone_id="UTC",
            bypass_csp=True,  # our freeze stylesheet must work on pages with a strict CSP
        )

    def _render(self, page: Any, request: CaptureRequest) -> bytes:
        settings = self._settings
        page.set_default_timeout(settings.timeout_ms)
        response = page.goto(request.target.location, wait_until="load")
        _ensure_healthy(request.target, response)
        if settings.disable_animations:
            page.add_style_tag(content=_FREEZE_CSS)
        page.evaluate("() => document.fonts.ready.then(() => true)")
        if settings.wait_for_selector:
            page.wait_for_selector(settings.wait_for_selector, state="visible")
        if request.script:
            page.evaluate(request.script)
        if settings.extra_wait_ms:
            page.wait_for_timeout(settings.extra_wait_ms)
        png: bytes = page.screenshot(
            full_page=settings.full_page,
            animations="disabled" if settings.disable_animations else "allow",
            caret="hide",
            mask=[page.locator(selector) for selector in request.mask],
            mask_color=settings.mask_color,
            type="png",
        )
        return png


def _close_quietly(context: Any, label: str) -> None:
    """Closing must never replace the real error (or turn a success into a failure)."""
    from playwright.sync_api import Error  # noqa: PLC0415

    try:
        context.close()
    except Error as exc:
        logger.warning("Could not close browser context for %s: %s", label, exc)
