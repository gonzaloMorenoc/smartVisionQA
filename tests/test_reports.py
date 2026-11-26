from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from smartvisionqa.ai.analyzer import RegionFinding
from smartvisionqa.ai.schema import Change
from smartvisionqa.config import DiffSettings
from smartvisionqa.diff import Region, compare_images
from smartvisionqa.report import write_reports
from smartvisionqa.report.html import render_index, render_outcome
from smartvisionqa.report.junit import render_junit
from smartvisionqa.report.markdown import render_markdown
from smartvisionqa.runner import Outcome, RunSummary, Verdict
from tests.conftest import make_png

EVIL = "<img src=x onerror=alert(1)>"


def failed_outcome(root: Path, name: str = "home") -> Outcome:
    folder = root / "comparisons" / name / "desktop"
    folder.mkdir(parents=True)
    before, after = make_png(), make_png(rects=[(10, 10, 20, 20, (255, 0, 0))])
    for file, data in (("before.png", before), ("after.png", after), ("diff.png", after)):
        (folder / file).write_bytes(data)
    change = Change(
        category="text",  # type: ignore[arg-type]
        description=f"Title | now {EVIL}",
        before="Old",
        after="New",
        severity="high",  # type: ignore[arg-type]
    )
    return Outcome(
        kind="comparison",
        name=name,
        viewport="desktop",
        before_label=f"a{EVIL}.html",
        after_label="https://example.com/?q=<script>",
        verdict=Verdict.FAILED,
        artifact_dir=folder,
        diff=compare_images(before, after, DiffSettings()),
        findings=(
            RegionFinding(region=Region(x=10, y=10, width=20, height=20), changes=(change,)),
        ),
        ai_status="ok",
        severity=change.severity,
        duration_s=1.5,
    )


def other_outcomes(root: Path) -> list[Outcome]:
    return [
        Outcome(
            kind="page",
            name="about",
            viewport="mobile",
            before_label="baseline",
            after_label="about.html",
            verdict=Verdict.PASSED,
            artifact_dir=root / "pages" / "about" / "mobile",
            ai_status="not_needed",
        ),
        Outcome(
            kind="page",
            name="broken",
            viewport="mobile",
            before_label="baseline",
            after_label="broken.html",
            verdict=Verdict.ERROR,
            artifact_dir=root / "pages" / "broken" / "mobile",
            error=f"Timeout {EVIL}",
        ),
        Outcome(
            kind="page",
            name="new",
            viewport="mobile",
            before_label="baseline",
            after_label="new.html",
            verdict=Verdict.MISSING_BASELINE,
            artifact_dir=root / "pages" / "new" / "mobile",
            error="No baseline yet.",
        ),
    ]


@pytest.fixture
def summary(tmp_path: Path) -> RunSummary:
    return RunSummary(
        outcomes=(failed_outcome(tmp_path), *other_outcomes(tmp_path)),
        output_dir=tmp_path,
        duration_s=3.2,
    )


class TestHtml:
    def test_outcome_report_escapes_everything_untrusted(self, summary: RunSummary) -> None:
        html = render_outcome(summary.outcomes[0], summary.output_dir)
        assert EVIL not in html
        assert "<script" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html

    def test_outcome_report_shows_images_changes_and_verdict(self, summary: RunSummary) -> None:
        html = render_outcome(summary.outcomes[0], summary.output_dir)
        for image in ("before.png", "after.png", "diff.png"):
            assert f'src="{image}"' in html
        assert "Old" in html and "New" in html
        assert "FAILED" in html.upper()
        assert "x=10" in html

    def test_error_report_shows_message(self, summary: RunSummary) -> None:
        html = render_outcome(summary.outcomes[2], summary.output_dir)
        assert "Timeout &lt;img" in html

    def test_index_links_every_outcome_relative(self, summary: RunSummary) -> None:
        html = render_index(summary)
        assert 'href="comparisons/home/desktop/report.html"' in html
        assert 'href="pages/about/mobile/report.html"' in html
        assert EVIL not in html


class TestJUnit:
    def test_junit_structure(self, summary: RunSummary) -> None:
        root = ET.fromstring(render_junit(summary))  # noqa: S314
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.attrib["tests"] == "4"
        assert suite.attrib["failures"] == "2"
        assert suite.attrib["errors"] == "1"
        cases = {case.attrib["name"]: case for case in suite.iter("testcase")}
        failure = cases["home[desktop]"].find("failure")
        assert failure is not None
        assert EVIL in (failure.text or "")  # escaped in XML, restored by the parser
        assert cases["broken[mobile]"].find("error") is not None
        assert cases["about[mobile]"].find("failure") is None


class TestMarkdown:
    def test_markdown_table(self, summary: RunSummary) -> None:
        md = render_markdown(summary)
        assert "| home | desktop |" in md
        assert "Title \\| now" in md
        assert "<img" not in md
        assert "❌" in md and "✅" in md and "💥" in md
        assert "1 passed" in md

    def test_markdown_links(self, summary: RunSummary) -> None:
        md = render_markdown(summary, link_base="https://pages.example/run")
        assert "https://pages.example/run/comparisons/home/desktop/report.html" in md


class TestWriteReports:
    def test_writes_all_artifacts(self, summary: RunSummary) -> None:
        paths = write_reports(summary)
        for path in (paths.index, paths.junit, paths.markdown, paths.json):
            assert path.is_file()
        assert (summary.output_dir / "comparisons/home/desktop/report.html").is_file()
        assert (summary.output_dir / "pages/broken/mobile/report.html").is_file()
