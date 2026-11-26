"""HTML reports rendered with Jinja2 (autoescape on: untrusted text can never inject markup)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from smartvisionqa import __version__
from smartvisionqa.report.presentation import (
    VERDICT_ICON,
    VERDICT_LABEL,
    headline,
    percent,
    report_href,
)
from smartvisionqa.runner import Outcome, RunSummary

_TEMPLATES = Path(__file__).parent / "templates"
_IMAGES = ("before.png", "after.png", "diff.png")

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["percent"] = percent
_env.globals.update(
    verdict_icon=VERDICT_ICON, verdict_label=VERDICT_LABEL, version=__version__, headline=headline
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def render_outcome(outcome: Outcome, output_root: Path) -> str:
    images = {name: (outcome.artifact_dir / name).is_file() for name in _IMAGES}
    index_href = Path(os.path.relpath(output_root / "index.html", outcome.artifact_dir)).as_posix()
    return _env.get_template("comparison.html.j2").render(
        outcome=outcome, images=images, index_href=index_href, generated_at=_now()
    )


def render_index(summary: RunSummary) -> str:
    rows = [(outcome, report_href(outcome, summary.output_dir)) for outcome in summary.outcomes]
    return _env.get_template("index.html.j2").render(
        summary=summary, rows=rows, generated_at=_now()
    )
