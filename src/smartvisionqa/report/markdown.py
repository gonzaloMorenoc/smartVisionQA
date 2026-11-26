"""GitHub-flavoured Markdown summary (job summary / PR comment)."""

from __future__ import annotations

from smartvisionqa.report.presentation import VERDICT_ICON, headline, percent, report_href
from smartvisionqa.runner import Outcome, RunSummary, Verdict

_MAX_CELL = 300


_ESCAPES = str.maketrans({"|": "\\|", "<": "&lt;", ">": "&gt;", "[": "\\[", "]": "\\]", "!": "\\!"})


def md_cell(text: str) -> str:
    """One-line table cell; untrusted text cannot break the table or inject links/images."""
    cleaned = " ".join(text.split()).translate(_ESCAPES)
    return cleaned if len(cleaned) <= _MAX_CELL else cleaned[: _MAX_CELL - 1] + "…"


def render_markdown(summary: RunSummary, link_base: str | None = None) -> str:
    counts = summary.counts
    parts = [
        f"{VERDICT_ICON[verdict]} {counts[verdict.value]} {verdict.value.replace('_', ' ')}"
        for verdict in Verdict
        if counts[verdict.value]
    ]
    status = (
        "✅ All visual checks passed"
        if summary.exit_code == 0
        else "❌ Visual checks need attention"
    )
    lines = [
        f"## SmartVisionQA — {status}",
        "",
        " · ".join(parts) if parts else "No checks configured.",
        "",
        "| Status | Name | Viewport | Changed | Severity | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_row(outcome, summary, link_base) for outcome in summary.outcomes)
    lines.append("")
    return "\n".join(lines)


def _row(outcome: Outcome, summary: RunSummary, link_base: str | None) -> str:
    name = md_cell(outcome.name)
    if link_base:
        name = f"[{name}]({link_base.rstrip('/')}/{report_href(outcome, summary.output_dir)})"
    changed = percent(outcome.diff.diff_ratio) if outcome.diff else "—"
    severity = outcome.severity.value if outcome.severity else "—"
    icon = f"{VERDICT_ICON[outcome.verdict]} {outcome.verdict.value.replace('_', ' ')}"
    return (
        f"| {icon} | {name} | {md_cell(outcome.viewport)} | {changed} | {severity} "
        f"| {md_cell(headline(outcome))} |"
    )
