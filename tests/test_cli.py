from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import ClassVar

import pytest

from smartvisionqa import cli
from smartvisionqa.ai.analyzer import RegionFinding
from smartvisionqa.capture import CaptureRequest
from smartvisionqa.config import AISettings, CaptureSettings
from smartvisionqa.diff import Region
from tests.conftest import make_png

WHITE = make_png()
CHANGED = make_png(rects=[(10, 10, 30, 20, (255, 0, 0))])


class FakeCapturer:
    instances: ClassVar[list[FakeCapturer]] = []

    def __init__(self, settings: CaptureSettings) -> None:
        self.settings = settings
        self.requests: list[CaptureRequest] = []
        FakeCapturer.instances.append(self)

    def __enter__(self) -> FakeCapturer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def capture(self, request: CaptureRequest) -> bytes:
        self.requests.append(request)
        if request.script and "noop" not in request.script:
            return CHANGED
        return CHANGED if "changed" in request.target.label else WHITE


class FakeAnalyzer:
    created_with: ClassVar[list[AISettings]] = []

    def __init__(self, settings: AISettings) -> None:
        FakeAnalyzer.created_with.append(settings)

    def check_available(self) -> str | None:
        return None

    def analyze(
        self, before: bytes, after: bytes, regions: Sequence[Region]
    ) -> tuple[RegionFinding, ...]:
        return ()


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeCapturer.instances = []
    FakeAnalyzer.created_with = []
    monkeypatch.setattr(cli, "make_capturer", FakeCapturer)
    monkeypatch.setattr(cli, "make_analyzer", FakeAnalyzer)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("a.html", "same.html", "changed.html"):
        (tmp_path / name).write_text("<html></html>")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestCompare:
    def test_identical_exit_zero_and_reports(self, site: Path) -> None:
        code = cli.main(["compare", "a.html", "same.html", "--no-ai", "--output", "out"])
        assert code == 0
        assert (site / "out" / "index.html").is_file()
        assert (site / "out" / "junit.xml").is_file()
        assert FakeAnalyzer.created_with == []

    def test_regression_exit_one(self, site: Path) -> None:
        assert cli.main(["compare", "a.html", "changed.html", "--output", "out"]) == 1
        summary = json.loads((site / "out" / "summary.json").read_text())
        assert summary["counts"]["failed"] == 1

    def test_viewports_masks_and_model_flags(self, site: Path) -> None:
        cli.main(
            [
                "compare",
                "a.html",
                "same.html",
                "--viewport",
                "390x844",
                "--viewport",
                "1280x800",
                "--mask",
                ".clock",
                "--model",
                "gemma3:4b",
                "--name",
                "home",
            ]
        )
        requests = FakeCapturer.instances[0].requests
        assert {r.viewport.name for r in requests} == {"390x844", "1280x800"}
        assert all(r.mask == (".clock",) for r in requests)
        assert FakeAnalyzer.created_with[0].model == "gemma3:4b"
        assert (site / "results" / "comparisons" / "home").is_dir()

    def test_missing_file_exit_two(self, site: Path) -> None:
        assert cli.main(["compare", "a.html", "nope.html", "--no-ai"]) == 2

    def test_bad_viewport_exit_two(self, site: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["compare", "a.html", "same.html", "--viewport", "huge"]) == 2
        assert "Viewport must look like" in capsys.readouterr().err

    def test_writes_github_step_summary(self, site: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        summary_file = site / "step-summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        cli.main(["compare", "a.html", "changed.html", "--no-ai"])
        assert "SmartVisionQA" in summary_file.read_text()


class TestRun:
    def config(self, site: Path, body: str) -> Path:
        path = site / "svqa.yaml"
        path.write_text(body)
        return path

    def test_run_with_config(self, site: Path) -> None:
        path = self.config(
            site,
            "ai: {enabled: false}\n"
            "comparisons:\n  - {name: c, before: a.html, after: changed.html}\n",
        )
        assert cli.main(["run", "--config", str(path)]) == 1
        assert FakeAnalyzer.created_with == []

    def test_baseline_lifecycle(self, site: Path) -> None:
        path = self.config(site, "pages:\n  - {name: home, target: a.html}\n")
        assert cli.main(["run", "--config", str(path), "--no-ai"]) == 1
        assert cli.main(["run", "--config", str(path), "--no-ai", "--update-baselines"]) == 0
        assert cli.main(["run", "--config", str(path), "--no-ai"]) == 0

    def test_invalid_config_exit_two(self, site: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = self.config(site, "nonsense: true\n")
        assert cli.main(["run", "--config", str(path)]) == 2
        assert "nonsense" in capsys.readouterr().err

    def test_empty_config_is_an_error(self, site: Path) -> None:
        assert cli.main(["run", "--config", str(self.config(site, "{}\n"))]) == 2


class TestEvaluate:
    def test_pixel_only_evaluation_passes_thresholds(self, site: Path) -> None:
        code = cli.main(["evaluate", "--target", "a.html", "--no-ai", "--output", "ev"])
        assert code == 0
        data = json.loads((site / "ev" / "evaluation.json").read_text())
        assert data["metrics"]["detection_recall"] == 1.0
        assert (site / "ev" / "evaluation.md").is_file()

    def test_threshold_miss_exit_one(self, site: Path) -> None:
        code = cli.main(["evaluate", "--target", "a.html", "--output", "ev", "--min-f1", "0.9"])
        assert code == 1

    def test_missing_target_exit_two(self, site: Path) -> None:
        assert cli.main(["evaluate", "--target", "nope.html", "--no-ai"]) == 2


def test_log_level_accepted_before_and_after_command(site: Path) -> None:
    assert cli.main(["--log-level", "error", "compare", "a.html", "same.html", "--no-ai"]) == 0
    assert cli.main(["compare", "a.html", "same.html", "--no-ai", "--log-level", "debug"]) == 0


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.main(["--version"])
    assert info.value.code == 0
    assert "smartvisionqa" in capsys.readouterr().out
