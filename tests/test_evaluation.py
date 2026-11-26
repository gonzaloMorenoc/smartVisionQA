from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from smartvisionqa.ai.analyzer import RegionFinding
from smartvisionqa.ai.schema import Category, Change
from smartvisionqa.capture import CaptureError, CaptureRequest
from smartvisionqa.config import DiffSettings, Viewport
from smartvisionqa.diff import Region
from smartvisionqa.evaluation.metrics import CaseResult, compute_metrics
from smartvisionqa.evaluation.mutations import DEFAULT_MUTATIONS, Mutation
from smartvisionqa.evaluation.runner import (
    EvaluationError,
    render_evaluation_markdown,
    run_evaluation,
)
from smartvisionqa.targets import Target
from tests.conftest import make_png

TARGET = Target(kind="file", location="file:///demo.html", label="demo.html")
VIEWPORT = Viewport(name="desktop", width=1280, height=800)
BASE = make_png()


def case(expected: Category | None, detected: bool, *predicted: Category) -> CaseResult:
    return CaseResult(
        mutation_id=f"{expected}-{predicted}",
        expected=expected,
        detected=detected,
        predicted=frozenset(predicted),
    )


class TestMetrics:
    def test_perfect_run(self) -> None:
        metrics = compute_metrics(
            [
                case(Category.TEXT, True, Category.TEXT),
                case(Category.STYLE, True, Category.STYLE),
                case(None, False),
            ]
        )
        assert metrics.detection_recall == 1.0
        assert metrics.false_positive_rate == 0.0
        assert metrics.category_accuracy == 1.0
        assert metrics.macro_f1 == 1.0
        assert set(metrics.per_category) == {"text", "style"}

    def test_mixed_run(self) -> None:
        metrics = compute_metrics(
            [
                case(Category.TEXT, True, Category.TEXT, Category.STYLE),  # tp text, fp style
                case(Category.STYLE, True, Category.LAYOUT),  # fn style, fp layout
                case(Category.LAYOUT, False),  # missed by pixel diff
                case(None, True, Category.ELEMENT),  # false positive on control
            ]
        )
        assert metrics.detection_recall == pytest.approx(2 / 3)
        assert metrics.false_positive_rate == 1.0
        assert metrics.category_accuracy == pytest.approx(1 / 3)
        text = metrics.per_category["text"]
        assert (text.precision, text.recall, text.f1) == (1.0, 1.0, 1.0)
        style = metrics.per_category["style"]
        assert style.precision == 0.0 and style.recall == 0.0
        assert metrics.per_category["layout"].recall == 0.0
        assert 0 < metrics.macro_f1 < 1

    def test_empty_inputs_do_not_divide_by_zero(self) -> None:
        metrics = compute_metrics([])
        assert metrics.detection_recall == 0.0
        assert metrics.false_positive_rate == 0.0
        assert metrics.macro_f1 == 0.0


class TestMutations:
    def test_default_mutations_cover_every_category_and_a_control(self) -> None:
        categories = {m.category for m in DEFAULT_MUTATIONS}
        assert categories == {*Category, None}
        assert len({m.id for m in DEFAULT_MUTATIONS}) == len(DEFAULT_MUTATIONS)
        assert all(m.script.startswith("() =>") for m in DEFAULT_MUTATIONS)


class ScriptCapturer:
    """Returns a changed image whenever a mutation script (other than the control) is applied."""

    def __init__(self, fail_id: str | None = None) -> None:
        self.fail_id = fail_id

    def capture(self, request: CaptureRequest) -> bytes:
        if request.script is None or "noop" in request.script:
            return BASE
        if self.fail_id and self.fail_id in request.script:
            raise CaptureError("selector missing")
        return make_png(rects=[(10, 10, 30, 30, (255, 0, 0))])


class EchoAnalyzer:
    """Pretends to be a model that always answers 'style'."""

    def __init__(self, problem: str | None = None) -> None:
        self.problem = problem

    def check_available(self) -> str | None:
        return self.problem

    def analyze(
        self, before: bytes, after: bytes, regions: Sequence[Region]
    ) -> tuple[RegionFinding, ...]:
        change = Change(category=Category.STYLE, description="Colour changed")
        return tuple(RegionFinding(region=r, changes=(change,)) for r in regions)


MUTATIONS = (
    Mutation("text-1", Category.TEXT, "t", "() => { /* text-1 */ }"),
    Mutation("style-1", Category.STYLE, "s", "() => { /* style-1 */ }"),
    Mutation("control", None, "c", "() => { /* noop */ }"),
)


class TestRunEvaluation:
    def test_pixel_only_evaluation(self) -> None:
        report = run_evaluation(TARGET, ScriptCapturer(), None, VIEWPORT, DiffSettings(), MUTATIONS)
        assert report.metrics.detection_recall == 1.0
        assert report.metrics.false_positive_rate == 0.0
        assert report.model is None
        assert all(not c.predicted for c in report.cases)

    def test_with_analyzer(self) -> None:
        report = run_evaluation(
            TARGET,
            ScriptCapturer(),
            EchoAnalyzer(),
            VIEWPORT,
            DiffSettings(),
            MUTATIONS,
            model="fake",
        )
        assert report.metrics.category_accuracy == 0.5
        assert report.metrics.per_category["style"].f1 == pytest.approx(2 / 3)
        markdown = render_evaluation_markdown(report)
        assert "fake" in markdown
        assert "| text-1 |" in markdown

    def test_unavailable_model_aborts(self) -> None:
        with pytest.raises(EvaluationError, match="down"):
            run_evaluation(
                TARGET, ScriptCapturer(), EchoAnalyzer("down"), VIEWPORT, DiffSettings(), MUTATIONS
            )

    def test_capture_errors_are_recorded_per_case(self) -> None:
        report = run_evaluation(
            TARGET, ScriptCapturer(fail_id="style-1"), None, VIEWPORT, DiffSettings(), MUTATIONS
        )
        failed = next(c for c in report.cases if c.mutation_id == "style-1")
        assert failed.error is not None
        assert failed.detected is False

    def test_report_serialises(self, tmp_path: Path) -> None:
        report = run_evaluation(TARGET, ScriptCapturer(), None, VIEWPORT, DiffSettings(), MUTATIONS)
        data = report.to_dict()
        assert data["metrics"]["detection_recall"] == 1.0
        assert len(data["cases"]) == 3
