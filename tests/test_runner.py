from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from smartvisionqa.ai.analyzer import RegionFinding
from smartvisionqa.ai.schema import Change, Severity
from smartvisionqa.baseline import BaselineStore
from smartvisionqa.capture import CaptureError, CaptureRequest
from smartvisionqa.config import Config, build_config
from smartvisionqa.diff import Region
from smartvisionqa.runner import Runner, RunSummary, Verdict, severity_from_ratio
from tests.conftest import make_png

WHITE = make_png()
CHANGED = make_png(rects=[(10, 10, 30, 20, (255, 0, 0))])


class FakeCapturer:
    def __init__(self, images: dict[str, bytes], fail_on: str | None = None) -> None:
        self.images = images
        self.fail_on = fail_on
        self.requests: list[CaptureRequest] = []

    def capture(self, request: CaptureRequest) -> bytes:
        self.requests.append(request)
        name = Path(request.target.label).name
        if name == self.fail_on:
            raise CaptureError(f"boom on {name}")
        return self.images[name]


class FakeAnalyzer:
    def __init__(self, problem: str | None = None, error: str | None = None) -> None:
        self.problem = problem
        self.error = error
        self.calls = 0

    def check_available(self) -> str | None:
        return self.problem

    def analyze(
        self, before: bytes, after: bytes, regions: Sequence[Region]
    ) -> tuple[RegionFinding, ...]:
        self.calls += 1
        if self.error:
            return tuple(RegionFinding(region=r, error=self.error) for r in regions)
        change = Change(category="style", description="Box is red now", severity="high")  # type: ignore[arg-type]
        return tuple(RegionFinding(region=r, changes=(change,)) for r in regions)


@pytest.fixture
def site(tmp_path: Path) -> Path:
    for name in ("a.html", "b.html", "c.html"):
        (tmp_path / name).write_text(f"<html>{name}</html>")
    return tmp_path


def make_config(site: Path, **data: Any) -> Config:
    return build_config({"base_dir": site, **data})


def comparison(before: str = "a.html", after: str = "b.html") -> dict[str, Any]:
    return {"comparisons": [{"name": "ab", "before": before, "after": after}]}


class TestComparisons:
    def test_identical_pages_pass_without_calling_ai(self, site: Path) -> None:
        analyzer = FakeAnalyzer()
        capturer = FakeCapturer({"a.html": WHITE, "b.html": WHITE})
        summary = Runner(make_config(site, **comparison()), capturer, analyzer).run()
        outcome = summary.outcomes[0]
        assert outcome.verdict is Verdict.PASSED
        assert outcome.ai_status == "not_needed"
        assert analyzer.calls == 0
        assert summary.exit_code == 0

    def test_changed_pages_fail_and_are_explained(self, site: Path) -> None:
        capturer = FakeCapturer({"a.html": WHITE, "b.html": CHANGED})
        summary = Runner(make_config(site, **comparison()), capturer, FakeAnalyzer()).run()
        outcome = summary.outcomes[0]
        assert outcome.verdict is Verdict.FAILED
        assert outcome.ai_status == "ok"
        assert outcome.severity is Severity.HIGH
        assert [c.description for c in outcome.changes] == ["Box is red now"]
        assert summary.exit_code == 1
        for artifact in ("before.png", "after.png", "diff.png", "result.json"):
            assert (outcome.artifact_dir / artifact).is_file()
        data = json.loads((outcome.artifact_dir / "result.json").read_text())
        assert data["verdict"] == "failed"
        assert data["findings"][0]["changes"][0]["description"] == "Box is red now"

    def test_without_ai_severity_comes_from_diff_ratio(self, site: Path) -> None:
        capturer = FakeCapturer({"a.html": WHITE, "b.html": CHANGED})
        outcome = Runner(make_config(site, **comparison()), capturer, None).run().outcomes[0]
        assert outcome.verdict is Verdict.FAILED
        assert outcome.ai_status == "disabled"
        assert outcome.severity is Severity.HIGH  # 600 / 10800 px > 5 %

    def test_unavailable_ai_degrades_gracefully_and_is_checked_once(self, site: Path) -> None:
        analyzer = FakeAnalyzer(problem="Ollama down")
        config = make_config(
            site,
            comparisons=[
                {"name": "ab", "before": "a.html", "after": "b.html"},
                {"name": "ac", "before": "a.html", "after": "c.html"},
            ],
        )
        capturer = FakeCapturer({"a.html": WHITE, "b.html": CHANGED, "c.html": CHANGED})
        summary = Runner(config, capturer, analyzer).run()
        assert all(o.verdict is Verdict.FAILED for o in summary.outcomes)
        assert all(o.ai_status == "unavailable: Ollama down" for o in summary.outcomes)
        assert analyzer.calls == 0

    def test_ai_errors_are_reported_as_failed_status(self, site: Path) -> None:
        capturer = FakeCapturer({"a.html": WHITE, "b.html": CHANGED})
        runner = Runner(make_config(site, **comparison()), capturer, FakeAnalyzer(error="bad"))
        assert runner.run().outcomes[0].ai_status == "failed"

    def test_capture_error_becomes_error_verdict(self, site: Path) -> None:
        capturer = FakeCapturer({"a.html": WHITE}, fail_on="b.html")
        summary = Runner(make_config(site, **comparison()), capturer, None).run()
        outcome = summary.outcomes[0]
        assert outcome.verdict is Verdict.ERROR
        assert outcome.error is not None
        assert "boom" in outcome.error
        assert summary.exit_code == 2

    def test_missing_target_file_becomes_error_verdict(self, site: Path) -> None:
        summary = Runner(
            make_config(site, **comparison(after="nope.html")), FakeCapturer({}), None
        ).run()
        assert summary.outcomes[0].verdict is Verdict.ERROR
        assert "not found" in (summary.outcomes[0].error or "")

    def test_every_viewport_and_masks_are_used(self, site: Path) -> None:
        config = make_config(
            site,
            viewports=[
                {"name": "m", "width": 390, "height": 800},
                {"name": "d", "width": 1280, "height": 800},
            ],
            capture={"mask": [".ad"]},
            comparisons=[{"name": "ab", "before": "a.html", "after": "b.html", "mask": [".clock"]}],
        )
        capturer = FakeCapturer({"a.html": WHITE, "b.html": WHITE})
        summary = Runner(config, capturer, None).run()
        assert [o.viewport for o in summary.outcomes] == ["m", "d"]
        assert capturer.requests[0].mask == (".ad", ".clock")
        assert {r.viewport.name for r in capturer.requests} == {"m", "d"}


class TestBaselines:
    def pages(self) -> dict[str, Any]:
        return {"pages": [{"name": "home", "target": "a.html"}], "baseline_dir": "baselines"}

    def test_missing_baseline_fails_until_approved(self, site: Path) -> None:
        config = make_config(site, **self.pages())
        capturer = FakeCapturer({"a.html": WHITE})
        summary = Runner(config, capturer, None).run()
        assert summary.outcomes[0].verdict is Verdict.MISSING_BASELINE
        assert summary.exit_code == 1
        assert not (site / "baselines").exists()

    def test_update_baselines_writes_and_passes(self, site: Path) -> None:
        config = make_config(site, **self.pages())
        summary = Runner(config, FakeCapturer({"a.html": WHITE}), None, update_baselines=True).run()
        assert summary.outcomes[0].verdict is Verdict.BASELINE_UPDATED
        assert summary.exit_code == 0
        assert BaselineStore(site / "baselines").load("home", "desktop") == WHITE

    def test_matching_baseline_passes_and_changed_page_fails(self, site: Path) -> None:
        config = make_config(site, **self.pages())
        BaselineStore(site / "baselines").save("home", "desktop", WHITE)
        assert Runner(config, FakeCapturer({"a.html": WHITE}), None).run().exit_code == 0
        outcome = Runner(config, FakeCapturer({"a.html": CHANGED}), None).run().outcomes[0]
        assert outcome.verdict is Verdict.FAILED
        assert outcome.before_label == "baseline"


class TestSummary:
    def test_counts_and_serialisation(self, site: Path) -> None:
        capturer = FakeCapturer({"a.html": WHITE, "b.html": CHANGED})
        summary = Runner(make_config(site, **comparison()), capturer, None).run()
        assert summary.counts == {
            "passed": 0,
            "failed": 1,
            "error": 0,
            "missing_baseline": 0,
            "baseline_updated": 0,
        }
        data = summary.to_dict()
        assert data["exit_code"] == 1
        assert data["outcomes"][0]["name"] == "ab"
        assert isinstance(summary, RunSummary)

    @pytest.mark.parametrize(
        ("ratio", "severity"),
        [(0.0001, Severity.LOW), (0.01, Severity.MEDIUM), (0.2, Severity.HIGH)],
    )
    def test_severity_from_ratio(self, ratio: float, severity: Severity) -> None:
        assert severity_from_ratio(ratio) is severity


class TestBaselineStore:
    def test_paths_are_slugified_inside_root(self, tmp_path: Path) -> None:
        store = BaselineStore(tmp_path)
        path = store.path_for("../../etc/passwd", "desk top")
        assert tmp_path in path.parents
        assert store.load("x", "y") is None
        saved = store.save("x", "y", b"png")
        assert saved.read_bytes() == b"png"
        assert store.load("x", "y") == b"png"
