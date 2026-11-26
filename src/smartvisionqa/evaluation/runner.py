"""Run the mutation suite: capture baseline, apply each mutation, diff, explain, score."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from smartvisionqa.capture import CaptureError, Capturer, CaptureRequest
from smartvisionqa.config import DiffSettings, Viewport
from smartvisionqa.diff import compare_images
from smartvisionqa.evaluation.metrics import CaseResult, EvaluationMetrics, compute_metrics
from smartvisionqa.evaluation.mutations import DEFAULT_MUTATIONS, Mutation
from smartvisionqa.imaging import ImageError
from smartvisionqa.report.markdown import md_cell
from smartvisionqa.runner import Analyzer
from smartvisionqa.targets import Target

logger = logging.getLogger(__name__)


class EvaluationError(RuntimeError):
    """The evaluation cannot run at all (e.g. the model under test is unavailable)."""


@dataclass(frozen=True)
class EvaluationReport:
    target: str
    viewport: str
    model: str | None
    metrics: EvaluationMetrics
    cases: tuple[CaseResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "viewport": self.viewport,
            "model": self.model,
            "metrics": self.metrics.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }


def run_evaluation(
    target: Target,
    capturer: Capturer,
    analyzer: Analyzer | None,
    viewport: Viewport,
    diff_settings: DiffSettings,
    mutations: Sequence[Mutation] = DEFAULT_MUTATIONS,
    model: str | None = None,
) -> EvaluationReport:
    if analyzer is not None:
        problem = analyzer.check_available()
        if problem:
            raise EvaluationError(problem)
    baseline = capturer.capture(CaptureRequest(target=target, viewport=viewport))
    cases = tuple(
        _run_case(target, capturer, analyzer, viewport, diff_settings, baseline, mutation)
        for mutation in mutations
    )
    return EvaluationReport(
        target=target.label,
        viewport=viewport.name,
        model=model if analyzer is not None else None,
        metrics=compute_metrics(cases),
        cases=cases,
    )


def _run_case(
    target: Target,
    capturer: Capturer,
    analyzer: Analyzer | None,
    viewport: Viewport,
    diff_settings: DiffSettings,
    baseline: bytes,
    mutation: Mutation,
) -> CaseResult:
    logger.info("Evaluating mutation %s", mutation.id)
    try:
        mutated = capturer.capture(
            CaptureRequest(target=target, viewport=viewport, script=mutation.script)
        )
        diff = compare_images(baseline, mutated, diff_settings)
    except (CaptureError, ImageError) as exc:
        logger.error("Mutation %s failed: %s", mutation.id, exc)
        return CaseResult(mutation.id, mutation.category, detected=False, error=str(exc))
    detected = diff.is_regression(diff_settings)
    if not detected or analyzer is None:
        return CaseResult(mutation.id, mutation.category, detected=detected)
    findings = analyzer.analyze(baseline, mutated, diff.regions)
    changes = [change for finding in findings for change in finding.changes]
    errors = [finding.error for finding in findings if finding.error]
    return CaseResult(
        mutation.id,
        mutation.category,
        detected=True,
        predicted=frozenset(change.category for change in changes),
        descriptions=tuple(change.description for change in changes),
        error="; ".join(errors) or None,
    )


def render_evaluation_markdown(report: EvaluationReport) -> str:
    m = report.metrics
    lines = [
        f"## SmartVisionQA evaluation — model: `{report.model or 'none (pixel diff only)'}`",
        "",
        f"Target `{report.target}` @ {report.viewport} · {m.cases} cases",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Detection recall (pixel diff) | {m.detection_recall:.0%} |",
        f"| False positive rate (controls) | {m.false_positive_rate:.0%} |",
        f"| Category accuracy (AI) | {m.category_accuracy:.0%} |",
        f"| Macro F1 (AI) | {m.macro_f1:.2f} |",
        "",
        "| Mutation | Expected | Detected | Predicted | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in report.cases:
        expected = case.expected.value if case.expected else "none"
        predicted = ", ".join(sorted(c.value for c in case.predicted)) or "—"
        note = md_cell(case.error or "; ".join(case.descriptions[:2]))
        detected = "✅" if case.detected else "—"
        lines.append(f"| {case.mutation_id} | {expected} | {detected} | {predicted} | {note} |")
    lines.append("")
    return "\n".join(lines)
