"""Orchestrates capture -> pixel diff -> (optional) AI explanation -> verdict."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np

from smartvisionqa.ai.analyzer import RegionFinding
from smartvisionqa.ai.schema import Change, Severity, max_severity
from smartvisionqa.baseline import BaselineStore
from smartvisionqa.capture import CaptureError, Capturer, CaptureRequest
from smartvisionqa.config import ComparisonSpec, Config, PageSpec, Viewport
from smartvisionqa.diff import DiffResult, Region, compare_images, render_diff_image
from smartvisionqa.imaging import ImageError
from smartvisionqa.naming import slugify
from smartvisionqa.targets import Target, TargetError, display_label, resolve_target

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_ERROR = 2
_HIGH_RATIO = 0.05
_MEDIUM_RATIO = 0.005
_EXPECTED_ERRORS = (TargetError, CaptureError, ImageError, OSError)
_ARTIFACTS = frozenset({"before.png", "after.png", "diff.png", "result.json", "report.html"})
_EMPTY_MASK = np.zeros((0, 0), dtype=bool)


class Analyzer(Protocol):
    def check_available(self) -> str | None: ...

    def analyze(
        self, before: bytes, after: bytes, regions: Sequence[Region]
    ) -> tuple[RegionFinding, ...]: ...


class Verdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    MISSING_BASELINE = "missing_baseline"
    BASELINE_UPDATED = "baseline_updated"


_FAILING = {Verdict.FAILED, Verdict.MISSING_BASELINE}


@dataclass(frozen=True)
class Outcome:
    kind: Literal["page", "comparison"]
    name: str
    viewport: str
    before_label: str
    after_label: str
    verdict: Verdict
    artifact_dir: Path
    diff: DiffResult | None = None
    findings: tuple[RegionFinding, ...] = ()
    ai_status: str = "disabled"
    severity: Severity | None = None
    error: str | None = None
    duration_s: float = 0.0

    @property
    def test_id(self) -> str:
        return f"{self.name}[{self.viewport}]"

    @property
    def changes(self) -> tuple[Change, ...]:
        return tuple(change for finding in self.findings for change in finding.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "viewport": self.viewport,
            "before": self.before_label,
            "after": self.after_label,
            "verdict": self.verdict.value,
            "severity": self.severity.value if self.severity else None,
            "ai_status": self.ai_status,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
            "diff": self.diff.to_dict() if self.diff else None,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class RunSummary:
    outcomes: tuple[Outcome, ...]
    output_dir: Path
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    duration_s: float = 0.0

    @property
    def counts(self) -> dict[str, int]:
        return {v.value: sum(o.verdict is v for o in self.outcomes) for v in Verdict}

    @property
    def exit_code(self) -> int:
        verdicts = {o.verdict for o in self.outcomes}
        if Verdict.ERROR in verdicts:
            return EXIT_ERROR
        if verdicts & _FAILING:
            return EXIT_REGRESSION
        return EXIT_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "exit_code": self.exit_code,
            "counts": self.counts,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }


def severity_from_ratio(ratio: float) -> Severity:
    if ratio >= _HIGH_RATIO:
        return Severity.HIGH
    if ratio >= _MEDIUM_RATIO:
        return Severity.MEDIUM
    return Severity.LOW


def _clear_artifacts(folder: Path) -> None:
    """Remove files from a previous run so reports never show stale screenshots."""
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        if path.is_file() and path.name in _ARTIFACTS:
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Cannot remove stale artifact %s: %s", path, exc)


@dataclass(frozen=True)
class _Job:
    kind: Literal["page", "comparison"]
    name: str
    viewport: Viewport
    mask: tuple[str, ...]
    artifact_dir: Path


class Runner:
    def __init__(
        self,
        config: Config,
        capturer: Capturer,
        analyzer: Analyzer | None,
        *,
        update_baselines: bool = False,
    ) -> None:
        self._config = config
        self._capturer = capturer
        self._analyzer = analyzer
        self._update_baselines = update_baselines
        self._baselines = BaselineStore(config.resolved_baseline_dir)
        self._output_dir = config.resolved_output_dir
        self._ai_problem: str | None = None
        self._ai_checked = False

    def run(self) -> RunSummary:
        start = time.perf_counter()
        outcomes = [
            self.check_page(page, viewport)
            for page in self._config.pages
            for viewport in self._config.viewports_for(page)
        ] + [
            self.compare(spec, viewport)
            for spec in self._config.comparisons
            for viewport in self._config.viewports_for(spec)
        ]
        return RunSummary(
            outcomes=tuple(outcomes),
            output_dir=self._output_dir,
            duration_s=time.perf_counter() - start,
        )

    def compare(self, spec: ComparisonSpec, viewport: Viewport) -> Outcome:
        job = self._job("comparison", spec.name, viewport, spec.mask)
        start = time.perf_counter()
        labels = (display_label(spec.before), display_label(spec.after))
        try:
            targets = (self._resolve(spec.before), self._resolve(spec.after))
            before, after = (self._capture(target, job) for target in targets)
        except _EXPECTED_ERRORS as exc:
            return self._error(job, *labels, exc, start)
        return self._evaluate(job, *labels, before, after, start)

    def check_page(self, page: PageSpec, viewport: Viewport) -> Outcome:
        job = self._job("page", page.name, viewport, page.mask)
        start = time.perf_counter()
        label = display_label(page.target)
        try:
            current = self._capture(self._resolve(page.target), job)
            baseline = self._baselines.load(page.name, viewport.name)
            if self._update_baselines or baseline is None:
                return self._new_baseline(job, label, current, start)
        except _EXPECTED_ERRORS as exc:
            return self._error(job, "baseline", label, exc, start)
        return self._evaluate(job, "baseline", label, baseline, current, start)

    def _job(
        self,
        kind: Literal["page", "comparison"],
        name: str,
        viewport: Viewport,
        mask: Sequence[str],
    ) -> _Job:
        folder = self._output_dir / f"{kind}s" / slugify(name) / slugify(viewport.name)
        _clear_artifacts(folder)
        return _Job(kind, name, viewport, (*self._config.capture.mask, *mask), folder)

    def _resolve(self, raw_target: str) -> Target:
        return resolve_target(raw_target, self._config.base_dir)

    def _capture(self, target: Target, job: _Job) -> bytes:
        logger.info("Capturing %s @ %s", target.label, job.viewport.name)
        return self._capturer.capture(
            CaptureRequest(target=target, viewport=job.viewport, mask=job.mask)
        )

    def _new_baseline(self, job: _Job, target: str, current: bytes, start: float) -> Outcome:
        job.artifact_dir.mkdir(parents=True, exist_ok=True)
        (job.artifact_dir / "after.png").write_bytes(current)
        if self._update_baselines:
            path = self._baselines.save(job.name, job.viewport.name, current)
            logger.info("Baseline written: %s", path)
            verdict, error = Verdict.BASELINE_UPDATED, None
        else:
            verdict = Verdict.MISSING_BASELINE
            error = "No baseline yet. Review after.png and run with --update-baselines to approve."
        return self._finish(
            Outcome(
                kind=job.kind,
                name=job.name,
                viewport=job.viewport.name,
                before_label="baseline",
                after_label=target,
                verdict=verdict,
                artifact_dir=job.artifact_dir,
                ai_status="not_needed",
                error=error,
                duration_s=time.perf_counter() - start,
            )
        )

    def _evaluate(
        self,
        job: _Job,
        before_label: str,
        after_label: str,
        before: bytes,
        after: bytes,
        start: float,
    ) -> Outcome:
        try:
            diff = compare_images(before, after, self._config.diff)
            job.artifact_dir.mkdir(parents=True, exist_ok=True)
            (job.artifact_dir / "before.png").write_bytes(before)
            (job.artifact_dir / "after.png").write_bytes(after)
            (job.artifact_dir / "diff.png").write_bytes(render_diff_image(after, diff))
            diff = replace(diff, mask=_EMPTY_MASK)  # don't keep a full-page mask per check
        except _EXPECTED_ERRORS as exc:
            return self._error(job, before_label, after_label, exc, start)

        regression = diff.is_regression(self._config.diff)
        findings: tuple[RegionFinding, ...] = ()
        if not regression:
            ai_status = "not_needed"
        else:
            findings, ai_status = self._explain(before, after, diff)
        changes = [change for finding in findings for change in finding.changes]
        severity = (
            (max_severity(changes) or severity_from_ratio(diff.diff_ratio)) if regression else None
        )
        return self._finish(
            Outcome(
                kind=job.kind,
                name=job.name,
                viewport=job.viewport.name,
                before_label=before_label,
                after_label=after_label,
                verdict=Verdict.FAILED if regression else Verdict.PASSED,
                artifact_dir=job.artifact_dir,
                diff=diff,
                findings=findings,
                ai_status=ai_status,
                severity=severity,
                duration_s=time.perf_counter() - start,
            )
        )

    def _explain(
        self, before: bytes, after: bytes, diff: DiffResult
    ) -> tuple[tuple[RegionFinding, ...], str]:
        if self._analyzer is None:
            return (), "disabled"
        if not self._ai_checked:
            self._ai_problem = self._analyzer.check_available()
            self._ai_checked = True
            if self._ai_problem:
                logger.warning("AI explanations disabled for this run: %s", self._ai_problem)
        if self._ai_problem:
            return (), f"unavailable: {self._ai_problem}"
        findings = self._analyzer.analyze(before, after, diff.regions)
        errors = sum(finding.error is not None for finding in findings)
        if findings and errors == len(findings):
            return findings, "failed"
        return findings, "partial" if errors else "ok"

    def _error(
        self, job: _Job, before_label: str, after_label: str, exc: Exception, start: float
    ) -> Outcome:
        logger.error("%s failed: %s", f"{job.name}[{job.viewport.name}]", exc)
        return self._finish(
            Outcome(
                kind=job.kind,
                name=job.name,
                viewport=job.viewport.name,
                before_label=before_label,
                after_label=after_label,
                verdict=Verdict.ERROR,
                artifact_dir=job.artifact_dir,
                ai_status="not_needed",
                error=str(exc),
                duration_s=time.perf_counter() - start,
            )
        )

    def _finish(self, outcome: Outcome) -> Outcome:
        try:
            outcome.artifact_dir.mkdir(parents=True, exist_ok=True)
            (outcome.artifact_dir / "result.json").write_text(
                json.dumps(outcome.to_dict(), indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Cannot write result for %s: %s", outcome.test_id, exc)
        return outcome
