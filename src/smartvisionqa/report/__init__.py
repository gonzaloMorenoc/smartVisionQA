"""Report writers: per-comparison HTML, index dashboard, JUnit XML, Markdown and JSON."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from smartvisionqa.report.html import render_index, render_outcome
from smartvisionqa.report.junit import render_junit
from smartvisionqa.report.markdown import render_markdown
from smartvisionqa.runner import RunSummary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportPaths:
    index: Path
    junit: Path
    markdown: Path
    json: Path


def write_reports(summary: RunSummary, link_base: str | None = None) -> ReportPaths:
    root = summary.output_dir
    root.mkdir(parents=True, exist_ok=True)
    for outcome in summary.outcomes:
        outcome.artifact_dir.mkdir(parents=True, exist_ok=True)
        _write(outcome.artifact_dir / "report.html", render_outcome(outcome, root))
    paths = ReportPaths(
        index=root / "index.html",
        junit=root / "junit.xml",
        markdown=root / "summary.md",
        json=root / "summary.json",
    )
    _write(paths.index, render_index(summary))
    _write(paths.junit, render_junit(summary))
    _write(paths.markdown, render_markdown(summary, link_base=link_base))
    _write(paths.json, json.dumps(summary.to_dict(), indent=2))
    logger.info("Reports written to %s", root)
    return paths


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
