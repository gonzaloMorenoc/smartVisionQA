"""Detection and classification metrics for evaluation runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from smartvisionqa.ai.schema import Category


@dataclass(frozen=True)
class CaseResult:
    mutation_id: str
    expected: Category | None
    detected: bool
    predicted: frozenset[Category] = frozenset()
    descriptions: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "expected": self.expected.value if self.expected else None,
            "detected": self.detected,
            "predicted": sorted(c.value for c in self.predicted),
            "descriptions": list(self.descriptions),
            "error": self.error,
        }


@dataclass(frozen=True)
class CategoryScore:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class EvaluationMetrics:
    cases: int
    detection_recall: float
    false_positive_rate: float
    category_accuracy: float
    macro_f1: float
    per_category: dict[str, CategoryScore] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return _ratio(2 * precision * recall, precision + recall)


def compute_metrics(results: Sequence[CaseResult]) -> EvaluationMetrics:
    mutated = [r for r in results if r.expected is not None]
    controls = [r for r in results if r.expected is None]
    tp = dict.fromkeys(Category, 0)
    fp = dict.fromkeys(Category, 0)
    fn = dict.fromkeys(Category, 0)
    support = dict.fromkeys(Category, 0)
    for result in results:
        for category in result.predicted:
            if category == result.expected:
                tp[category] += 1
            else:
                fp[category] += 1
        if result.expected is not None:
            support[result.expected] += 1
            if result.expected not in result.predicted:
                fn[result.expected] += 1
    per_category = {}
    for category in Category:
        if not support[category]:
            continue
        precision = _ratio(tp[category], tp[category] + fp[category])
        recall = _ratio(tp[category], tp[category] + fn[category])
        per_category[category.value] = CategoryScore(
            precision=precision, recall=recall, f1=_f1(precision, recall), support=support[category]
        )
    return EvaluationMetrics(
        cases=len(results),
        detection_recall=_ratio(sum(r.detected for r in mutated), len(mutated)),
        false_positive_rate=_ratio(sum(r.detected for r in controls), len(controls)),
        category_accuracy=_ratio(sum(r.expected in r.predicted for r in mutated), len(mutated)),
        macro_f1=_ratio(sum(s.f1 for s in per_category.values()), len(per_category)),
        per_category=per_category,
    )
