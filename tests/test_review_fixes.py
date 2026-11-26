"""Regression tests for defects found in code review."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from smartvisionqa import cli
from smartvisionqa.ai.analyzer import RegionFinding, VisionAnalyzer
from smartvisionqa.ai.parsing import parse_region_analysis
from smartvisionqa.ai.schema import Category, Change, is_noop
from smartvisionqa.capture import CaptureRequest
from smartvisionqa.config import AISettings, ConfigError, DiffSettings, build_config
from smartvisionqa.diff import Region, compare_images
from smartvisionqa.evaluation.metrics import CaseResult, compute_metrics
from smartvisionqa.evaluation.runner import EvaluationReport, render_evaluation_markdown
from smartvisionqa.naming import slugify
from smartvisionqa.report.junit import render_junit
from smartvisionqa.report.markdown import render_markdown
from smartvisionqa.runner import Outcome, Runner, RunSummary, Verdict
from smartvisionqa.targets import TargetError, display_label, resolve_target
from tests.conftest import make_png
from tests.test_ai import FakeClient, ok_response
from tests.test_cli import FakeAnalyzer, FakeCapturer

WHITE = make_png()
CHANGED = make_png(rects=[(10, 10, 30, 20, (255, 0, 0))])


class TestSlugCollisions:
    def test_non_ascii_names_do_not_collapse(self) -> None:
        assert slugify("首页") != slugify("登录")
        assert slugify("首页").startswith("item-")

    def test_config_rejects_names_that_share_a_folder(self) -> None:
        with pytest.raises(ConfigError, match="same folder"):
            build_config(
                {"pages": [{"name": "Home", "target": "a"}, {"name": "home", "target": "b"}]}
            )
        with pytest.raises(ConfigError, match="same folder"):
            build_config(
                {
                    "comparisons": [
                        {"name": "a b", "before": "x", "after": "y"},
                        {"name": "a/b", "before": "x", "after": "y"},
                    ]
                }
            )

    def test_empty_viewport_subset_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="viewports"):
            build_config({"pages": [{"name": "p", "target": "a", "viewports": []}]})


class TestTargets:
    def test_credentials_and_query_are_redacted_from_labels(self, tmp_path: Path) -> None:
        target = resolve_target("https://user:secret@example.com/a?token=abc", tmp_path)
        assert target.location == "https://user:secret@example.com/a?token=abc"
        assert "secret" not in target.label
        assert "abc" not in target.label
        assert target.label == "https://example.com/a?…"

    def test_display_label_redacts_without_validating(self) -> None:
        assert display_label("https://u:p@h.io:8080/x#frag") == "https://h.io:8080/x"
        assert display_label("demo/page.html") == "demo/page.html"

    def test_missing_scheme_gets_helpful_message(self, tmp_path: Path) -> None:
        with pytest.raises(TargetError, match="http://"):
            resolve_target("localhost:3000/app", tmp_path)


class TestNoops:
    def test_same_label_but_moved_is_a_real_change(self) -> None:
        change = Change(
            category=Category.LAYOUT,
            description="Button moved 20px right",
            before="Buy now",
            after="Buy now",
        )
        assert not is_noop(change)


class TestParsingResilience:
    def test_percentage_confidence_is_rescaled(self) -> None:
        raw = json.dumps({"changes": [{"category": "text", "description": "x", "confidence": 90}]})
        assert parse_region_analysis(raw).changes[0].confidence == pytest.approx(0.9)

    def test_one_invalid_item_does_not_discard_the_region(self) -> None:
        raw = json.dumps(
            {
                "changes": [
                    {"category": "text", "description": ""},
                    {"category": "style", "description": "Blue"},
                ]
            }
        )
        assert [c.description for c in parse_region_analysis(raw).changes] == ["Blue"]


class TestRetries:
    def test_seed_varies_per_attempt_and_transport_errors_are_retried(self) -> None:
        client = FakeClient([ConnectionError("blip"), "garbage", ok_response("ok")])
        finding = VisionAnalyzer(AISettings(max_retries=2, seed=10), client=client).analyze(
            make_png(), make_png(), [Region(x=0, y=0, width=10, height=10)]
        )[0]
        assert finding.changes[0].description == "ok"
        assert [c["options"]["seed"] for c in client.calls] == [10, 11, 12]


class TestDiffSensitivity:
    def test_default_settings_never_ignore_a_real_change(self) -> None:
        after = make_png(rects=[(50, 50, 2, 2, (0, 0, 0))])
        result = compare_images(WHITE, after, DiffSettings())
        assert result.is_regression(DiffSettings())


class Capturer:
    def __init__(self, images: dict[str, bytes]) -> None:
        self.images = images

    def capture(self, request: CaptureRequest) -> bytes:
        return self.images[Path(request.target.label).name]


class TestRunnerHygiene:
    def site(self, tmp_path: Path) -> Path:
        for name in ("a.html", "b.html"):
            (tmp_path / name).write_text("x")
        return tmp_path

    def test_stale_images_are_removed_when_a_later_run_errors(self, tmp_path: Path) -> None:
        site = self.site(tmp_path)
        data: dict[str, Any] = {
            "base_dir": site,
            "comparisons": [{"name": "ab", "before": "a.html", "after": "b.html"}],
        }
        first = Runner(
            build_config(data), Capturer({"a.html": WHITE, "b.html": CHANGED}), None
        ).run()
        folder = first.outcomes[0].artifact_dir
        assert (folder / "diff.png").exists()
        (site / "b.html").unlink()
        second = Runner(build_config(data), Capturer({"a.html": WHITE}), None).run()
        assert second.outcomes[0].verdict is Verdict.ERROR
        assert not (folder / "diff.png").exists()
        assert not (folder / "before.png").exists()

    def test_masks_are_not_kept_in_memory(self, tmp_path: Path) -> None:
        site = self.site(tmp_path)
        data = {
            "base_dir": site,
            "comparisons": [{"name": "ab", "before": "a.html", "after": "b.html"}],
        }
        outcome = (
            Runner(build_config(data), Capturer({"a.html": WHITE, "b.html": CHANGED}), None)
            .run()
            .outcomes[0]
        )
        assert outcome.diff is not None
        assert outcome.diff.mask.size == 0
        assert outcome.diff.changed_pixels == 600


class TestCliRobustness:
    def test_unexpected_os_error_exits_two_not_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli, "make_capturer", FakeCapturer)
        monkeypatch.chdir(tmp_path)
        for name in ("a.html", "same.html"):
            (tmp_path / name).write_text("x")
        (tmp_path / "blocker").write_text("I am a file, not a folder")
        assert cli.main(["compare", "a.html", "same.html", "--no-ai", "--output", "blocker"]) == 2

    def test_model_can_come_from_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        FakeAnalyzer.created_with = []
        monkeypatch.setattr(cli, "make_capturer", FakeCapturer)
        monkeypatch.setattr(cli, "make_analyzer", FakeAnalyzer)
        monkeypatch.setenv("SVQA_MODEL", "qwen2.5vl:3b")
        monkeypatch.chdir(tmp_path)
        for name in ("a.html", "changed.html"):
            (tmp_path / name).write_text("x")
        cli.main(["compare", "a.html", "changed.html"])
        assert FakeAnalyzer.created_with[0].model == "qwen2.5vl:3b"

    def test_compare_keeps_config_relative_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli, "make_capturer", FakeCapturer)
        conf = tmp_path / "conf"
        conf.mkdir()
        (conf / "c.yaml").write_text("output_dir: out\n")
        work = tmp_path / "work"
        work.mkdir()
        for name in ("a.html", "same.html"):
            (work / name).write_text("x")
        monkeypatch.chdir(work)
        assert (
            cli.main(
                ["compare", "a.html", "same.html", "--no-ai", "--config", str(conf / "c.yaml")]
            )
            == 0
        )
        assert (conf / "out" / "index.html").is_file()

    def test_evaluate_fails_when_the_model_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Broken:
            def __init__(self, settings: AISettings) -> None: ...
            def check_available(self) -> str | None:
                return None

            def analyze(
                self, before: bytes, after: bytes, regions: Sequence[Region]
            ) -> tuple[RegionFinding, ...]:
                return tuple(RegionFinding(region=r, error="model exploded") for r in regions)

        monkeypatch.setattr(cli, "make_capturer", FakeCapturer)
        monkeypatch.setattr(cli, "make_analyzer", Broken)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.html").write_text("x")
        assert cli.main(["evaluate", "--target", "a.html", "--output", "ev"]) == 2


class TestReportEscaping:
    def outcome(self, tmp_path: Path, text: str) -> Outcome:
        change = Change(category=Category.TEXT, description=text)
        return Outcome(
            kind="comparison",
            name="n",
            viewport="d",
            before_label="a",
            after_label="b",
            verdict=Verdict.FAILED,
            artifact_dir=tmp_path / "x",
            findings=(
                RegionFinding(region=Region(x=0, y=0, width=1, height=1), changes=(change,)),
            ),
        )

    def test_junit_strips_xml_invalid_control_characters(self, tmp_path: Path) -> None:
        summary = RunSummary(
            outcomes=(self.outcome(tmp_path, "bad\x0bchar\x00"),), output_dir=tmp_path
        )
        ET.fromstring(render_junit(summary))  # noqa: S314 - must not raise

    def test_markdown_neutralises_links_and_images(self, tmp_path: Path) -> None:
        summary = RunSummary(
            outcomes=(self.outcome(tmp_path, "![x](https://evil/p.png) [y](https://evil)"),),
            output_dir=tmp_path,
        )
        md = render_markdown(summary)
        assert "![x](" not in md and "[y](" not in md

    def test_evaluation_markdown_keeps_rows_on_one_line(self) -> None:
        cases = (
            CaseResult("m1", Category.TEXT, False, error="Timeout\nCall log:\n  - navigating | x"),
        )
        report = EvaluationReport(
            target="t", viewport="d", model=None, metrics=compute_metrics(cases), cases=cases
        )
        row = next(
            line
            for line in render_evaluation_markdown(report).splitlines()
            if line.startswith("| m1")
        )
        assert "Call log" in row and "\\|" in row
