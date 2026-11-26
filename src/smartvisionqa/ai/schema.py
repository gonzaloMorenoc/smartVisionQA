"""Structured output contract for the vision model, plus no-op filtering."""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(str, Enum):
    LAYOUT = "layout"
    TEXT = "text"
    STYLE = "style"
    ELEMENT = "element"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


def _enum_text(value: Any) -> str:
    """Normalise enum members and loose strings ("Style ") to their lowercase value."""
    raw = value.value if isinstance(value, Enum) else value
    return str(raw).strip().lower()


class Change(BaseModel):
    """One concrete visual difference inside a region."""

    model_config = ConfigDict(frozen=True)

    category: Category = Field(description="layout | text | style | element")
    description: str = Field(min_length=1, max_length=1000, description="What changed, concisely")
    before: str = Field(default="", max_length=500, description="Value/appearance in BEFORE")
    after: str = Field(default="", max_length=500, description="Value/appearance in AFTER")
    severity: Severity = Field(default=Severity.MEDIUM, description="low | medium | high")
    confidence: float = Field(default=0.5, ge=0, le=1, description="0-1 certainty")

    @field_validator("category", mode="before")
    @classmethod
    def _unknown_category_is_element(cls, value: Any) -> Any:
        text = _enum_text(value)
        return text if text in {c.value for c in Category} else Category.ELEMENT.value

    @field_validator("severity", mode="before")
    @classmethod
    def _unknown_severity_is_medium(cls, value: Any) -> Any:
        text = _enum_text(value)
        return text if text in {s.value for s in Severity} else Severity.MEDIUM.value

    @field_validator("confidence", mode="before")
    @classmethod
    def _rescale_confidence(cls, value: Any) -> Any:
        """Models often answer 90 meaning 90 %: rescale percentages, clamp the rest."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        number = float(value) / 100 if 1 < value <= 100 else float(value)
        return min(1.0, max(0.0, number))

    @field_validator("description", "before", "after", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class RegionAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    changes: tuple[Change, ...] = ()


def response_schema() -> dict[str, Any]:
    """JSON schema passed to Ollama's ``format`` (structured outputs)."""
    return RegionAnalysis.model_json_schema()


_NOOP = re.compile(
    r"(none|n/?a|nothing|identical|unchanged|same|no difference|"
    r"no (visible |visual |noticeable )?(changes?|differences?)( (were )?(detected|found))?|"
    r"(the )?(pages?|images?|versions?|regions?|screenshots?) (are|is|look|looks|appear|appears)"
    r" (identical|the same|unchanged))"
)
_V1_V2 = re.compile(
    r"^(?:v1|before|version 1)\s+(?:has|shows|is|displays|uses)\s+(?P<a>.+?),\s*"
    r"(?:while |but |and |whereas )?(?:v2|after|version 2)\s+(?:has|shows|is|displays|uses)\s+"
    r"(?P<b>.+)$"
)
_TRAILING = " .!;:\"'"


def _norm(text: str) -> str:
    return " ".join(text.casefold().split()).strip(_TRAILING)


def is_noop(change: Change) -> bool:
    """True when a 'change' actually states that nothing changed (a common LLM failure)."""
    description = _norm(change.description)
    if _NOOP.fullmatch(description):
        return True
    match = _V1_V2.match(description)
    return bool(match and _norm(match.group("a")) == _norm(match.group("b")))


def normalize_changes(changes: Iterable[Change]) -> tuple[Change, ...]:
    """Drop no-ops and duplicates while keeping the model's order."""
    seen: set[tuple[Category, str]] = set()
    result = []
    for change in changes:
        key = (change.category, _norm(change.description))
        if is_noop(change) or key in seen:
            continue
        seen.add(key)
        result.append(change)
    return tuple(result)


def max_severity(changes: Iterable[Change]) -> Severity | None:
    ranked = sorted((c.severity for c in changes), key=lambda s: s.rank)
    return ranked[-1] if ranked else None
