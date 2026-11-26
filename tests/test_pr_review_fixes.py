"""Regression tests for defects found in the PR #10 review."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Error as PlaywrightError

from smartvisionqa import cli, imaging
from smartvisionqa.ai.analyzer import RegionFinding, VisionAnalyzer
from smartvisionqa.capture import CaptureError, CaptureRequest, PlaywrightCapturer
from smartvisionqa.config import AISettings, CaptureSettings, DiffSettings, Viewport, build_config
from smartvisionqa.diff import Region
from smartvisionqa.evaluation.mutations import Mutation
from smartvisionqa.evaluation.runner import run_evaluation
from smartvisionqa.runner import Runner, Verdict
from smartvisionqa.targets import Target, TargetError, display_label, resolve_target
from tests.conftest import make_png
from tests.test_ai import FakeClient, ok_response
from tests.test_cli import FakeCapturer

WHITE = make_png()
VIEWPORT = Viewport(name="desktop", width=1280, height=800)


class TestMalformedUrls:
    @pytest.mark.parametrize("raw", ["http://host:99999/", "http://[::1/x"])
    def test_resolve_target_raises_target_error(self, raw: str, tmp_path: Path) -> None:
        with pytest.raises(TargetError):
            resolve_target(raw, tmp_path)

    @pytest.mark.parametrize("raw", ["http://u:pw@host:99999/a?t=1", "http://u:pw@[::1/x?t=1"])
    def test_display_label_never_raises_nor_leaks(self, raw: str) -> None:
        label = display_label(raw)
        assert "pw" not in label
        assert "t=1" not in label

    def test_one_bad_url_does_not_abort_the_run(self, tmp_path: Path) -> None:
        (tmp_path / "a.html").write_text("x")
        config = build_config(
            {
                "base_dir": tmp_path,
                "comparisons": [
                    {"name": "bad", "before": "http://staging:99999/", "after": "a.html"},
                    {"name": "good", "before": "a.html", "after": "a.html"},
                ],
            }
        )

        class Same:
            def capture(self, request: CaptureRequest) -> bytes:
                return WHITE

        summary = Runner(config, Same(), None).run()
        assert [o.verdict for o in summary.outcomes] == [Verdict.ERROR, Verdict.PASSED]


class TestCompareDefaultName:
    def test_default_name_never_contains_query_strings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: list[Any] = []

        def fake_execute(config: Any, update_baselines: bool, link_base: str | None) -> int:
            recorded.append(config)
            return 0

        monkeypatch.setattr(cli, "_execute", fake_execute)
        monkeypatch.chdir(tmp_path)
        cli.main(
            [
                "compare",
                "https://u:pw@shop.io/checkout?token=SECRET",
                "https://shop2.io/checkout?token=SECRET#x",
                "--no-ai",
            ]
        )
        name = recorded[0].comparisons[0].name
        assert "SECRET" not in name and "pw" not in name
        assert "checkout" in name


class FakePage:
    def __init__(self, fail_screenshot: bool) -> None:
        self.fail_screenshot = fail_screenshot

    def set_default_timeout(self, ms: int) -> None: ...

    def goto(self, url: str, wait_until: str) -> None:
        return None

    def add_style_tag(self, content: str) -> None: ...

    def evaluate(self, script: str) -> None: ...

    def locator(self, selector: str) -> str:
        return selector

    def screenshot(self, **kwargs: Any) -> bytes:
        if self.fail_screenshot:
            raise PlaywrightError("renderer crashed")
        return WHITE


class FakeContext:
    def __init__(self, fail_screenshot: bool, fail_close: bool) -> None:
        self.page = FakePage(fail_screenshot)
        self.fail_close = fail_close

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        if self.fail_close:
            raise PlaywrightError("Target closed")


class FakeBrowser:
    def __init__(self, fail_new_context: bool = False, **context: bool) -> None:
        self.fail_new_context = fail_new_context
        self.context = context

    def new_context(self, **kwargs: Any) -> FakeContext:
        if self.fail_new_context:
            raise PlaywrightError("browser has been closed")
        return FakeContext(**self.context)


def capture_with(browser: FakeBrowser) -> bytes:
    capturer = PlaywrightCapturer(CaptureSettings())
    capturer._browser = browser
    target = Target(kind="file", location="file:///x.html", label="x.html")
    return capturer.capture(CaptureRequest(target=target, viewport=VIEWPORT))


class TestCaptureErrorsAreContained:
    def test_new_context_failure_is_a_capture_error(self) -> None:
        with pytest.raises(CaptureError, match="browser has been closed"):
            capture_with(FakeBrowser(fail_new_context=True))

    def test_close_failure_does_not_mask_the_real_error(self) -> None:
        with pytest.raises(CaptureError, match="renderer crashed"):
            capture_with(FakeBrowser(fail_screenshot=True, fail_close=True))

    def test_close_failure_after_success_is_only_logged(self) -> None:
        assert capture_with(FakeBrowser(fail_screenshot=False, fail_close=True)) == WHITE


class TestEvaluationMasks:
    def test_masks_reach_every_capture(self) -> None:
        requests: list[CaptureRequest] = []

        class Recorder:
            def capture(self, request: CaptureRequest) -> bytes:
                requests.append(request)
                return WHITE

        target = Target(kind="file", location="file:///x.html", label="x.html")
        mutations = (Mutation("control", None, "c", "() => {}"),)
        run_evaluation(
            target, Recorder(), None, VIEWPORT, DiffSettings(), mutations, mask=(".clock",)
        )
        assert [r.mask for r in requests] == [(".clock",), (".clock",)]

    def test_cli_passes_config_masks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli, "make_capturer", FakeCapturer)
        FakeCapturer.instances = []
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.html").write_text("x")
        (tmp_path / "c.yaml").write_text("capture: {mask: ['.clock']}\n")
        cli.main(["evaluate", "--target", "a.html", "--no-ai", "--config", "c.yaml"])
        assert all(r.mask == (".clock",) for r in FakeCapturer.instances[0].requests)


class TestAnalyzerDecodesOnce:
    def test_full_images_are_decoded_once_per_comparison(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        original = imaging.load_rgb

        def counting(data: bytes, *args: Any, **kwargs: Any) -> Any:
            calls.append(len(data))
            return original(data, *args, **kwargs)

        monkeypatch.setattr(imaging, "load_rgb", counting)
        regions: Sequence[Region] = [Region(x=i * 10, y=0, width=5, height=5) for i in range(4)]
        client = FakeClient([ok_response("x")] * 4)
        findings: tuple[RegionFinding, ...] = VisionAnalyzer(
            AISettings(max_regions=4), client=client
        ).analyze(make_png(), make_png(), regions)
        assert len(findings) == 4
        assert len(calls) == 2
