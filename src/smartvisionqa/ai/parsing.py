"""Tolerant parsing of model output into a validated :class:`RegionAnalysis`.

Structured outputs make most of this unnecessary, but models (or older Ollama servers)
still drift. Every accepted shape is explicit; anything else raises instead of silently
becoming "no changes".
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from smartvisionqa.ai.schema import Category, Change, RegionAnalysis

_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)
_LEGACY_KEYS = {f"{category.value}_changes": category for category in Category}


class AIResponseError(ValueError):
    """The model answered something that is not a valid analysis."""


def parse_region_analysis(raw: str) -> RegionAnalysis:
    data = _load_json(raw)
    if isinstance(data.get("differences"), dict):
        data = data["differences"]
    if "changes" in data:
        items = data["changes"]
        if not isinstance(items, list):
            raise AIResponseError("'changes' must be a list")
        changes = [_coerce_item(item, Category.ELEMENT) for item in items]
    elif _LEGACY_KEYS.keys() & data.keys():
        changes = _from_legacy(data)
    else:
        raise AIResponseError(f"No 'changes' key in model output: {sorted(data)}")
    return RegionAnalysis(changes=_validate_items([c for c in changes if c]))


def _validate_items(items: list[dict[str, Any]]) -> tuple[Change, ...]:
    """Keep every valid item; only fail when the model produced items and none is usable."""
    valid: list[Change] = []
    problems: list[str] = []
    for item in items:
        try:
            valid.append(Change.model_validate(item))
        except ValidationError as exc:
            problems.append(str(exc.errors()[0]["msg"]))
    if items and not valid:
        raise AIResponseError(f"No valid change in model output: {problems[:3]}")
    return tuple(valid)


def _load_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise AIResponseError("Empty model output")
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise AIResponseError("Model output contains no JSON object") from None
        try:
            data, _ = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError as exc:
            raise AIResponseError(f"Model output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIResponseError(f"Expected a JSON object, got {type(data).__name__}")
    return data


def _from_legacy(data: dict[str, Any]) -> list[dict[str, Any] | None]:
    changes: list[dict[str, Any] | None] = []
    for key, category in _LEGACY_KEYS.items():
        value = data.get(key)
        items = value if isinstance(value, list) else [value] if value else []
        changes.extend(_coerce_item(item, category) for item in items)
    return changes


def _coerce_item(item: Any, category: Category) -> dict[str, Any] | None:
    if isinstance(item, str):
        return {"category": category.value, "description": item} if item.strip() else None
    if isinstance(item, dict):
        result = dict(item)
        result.setdefault("category", category.value)
        if not str(result.get("description", "")).strip():
            texts = [str(v) for k, v in item.items() if k != "category" and isinstance(v, str)]
            if not texts:
                return None
            result["description"] = "; ".join(texts)
        return result
    return None
