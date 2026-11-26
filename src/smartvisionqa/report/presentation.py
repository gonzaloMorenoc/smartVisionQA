"""Shared presentation helpers (labels, icons, formatting) for every report format."""

from __future__ import annotations

from pathlib import Path

from smartvisionqa.runner import Outcome, Verdict

VERDICT_ICON = {
    Verdict.PASSED: "✅",
    Verdict.FAILED: "❌",
    Verdict.ERROR: "💥",
    Verdict.MISSING_BASELINE: "🆕",
    Verdict.BASELINE_UPDATED: "📸",
}
VERDICT_LABEL = {
    Verdict.PASSED: "Passed",
    Verdict.FAILED: "Failed",
    Verdict.ERROR: "Error",
    Verdict.MISSING_BASELINE: "Missing baseline",
    Verdict.BASELINE_UPDATED: "Baseline updated",
}


def percent(ratio: float) -> str:
    if ratio == 0:
        return "0%"
    return f"{ratio * 100:.3f}%" if ratio < 0.0001 else f"{ratio * 100:.2f}%"


def report_href(outcome: Outcome, root: Path) -> str:
    return (outcome.artifact_dir / "report.html").relative_to(root).as_posix()


def headline(outcome: Outcome, limit: int = 3) -> str:
    """Short plain-text summary of what changed (or why it failed)."""
    if outcome.error:
        return outcome.error
    descriptions = [change.description for change in outcome.changes][:limit]
    if descriptions:
        extra = len(outcome.changes) - len(descriptions)
        return "; ".join(descriptions) + (f" (+{extra} more)" if extra > 0 else "")
    if outcome.diff and outcome.verdict is Verdict.FAILED:
        return f"{len(outcome.diff.regions)} changed region(s), AI: {outcome.ai_status}"
    return ""
