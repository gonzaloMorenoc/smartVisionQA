"""Ollama-backed analyzer with structured outputs, deterministic options and retries."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from smartvisionqa import imaging
from smartvisionqa.ai.parsing import AIResponseError, parse_region_analysis
from smartvisionqa.ai.prompt import build_prompt
from smartvisionqa.ai.schema import Change, normalize_changes, response_schema
from smartvisionqa.config import AISettings
from smartvisionqa.diff import Region

logger = logging.getLogger(__name__)


class ChatClient(Protocol):
    """The subset of ``ollama.Client`` we depend on (eases testing and swapping)."""

    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        format: dict[str, Any],
        options: Mapping[str, Any],
    ) -> Any: ...

    def show(self, model: str) -> Any: ...


@dataclass(frozen=True)
class RegionFinding:
    region: Region
    changes: tuple[Change, ...] = ()
    error: str | None = None
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region.to_dict(),
            "changes": [change.model_dump(mode="json") for change in self.changes],
            "error": self.error,
            "attempts": self.attempts,
        }


def default_client(settings: AISettings) -> ChatClient:
    import ollama  # noqa: PLC0415 - optional at import time so --no-ai never needs it

    client: ChatClient = ollama.Client(host=settings.host, timeout=settings.timeout_s)
    return client


class VisionAnalyzer:
    def __init__(self, settings: AISettings, client: ChatClient | None = None) -> None:
        self._settings = settings
        self._client = client if client is not None else default_client(settings)

    @property
    def settings(self) -> AISettings:
        return self._settings

    def check_available(self) -> str | None:
        """Return a human-readable problem, or ``None`` when the model is ready."""
        try:
            self._client.show(self._settings.model)
        except Exception as exc:
            return (
                f"Ollama model {self._settings.model!r} is not available ({exc}). "
                f"Start Ollama and run: ollama pull {self._settings.model}"
            )
        return None

    def analyze(
        self, before: bytes, after: bytes, regions: Sequence[Region]
    ) -> tuple[RegionFinding, ...]:
        selected = list(regions)[: self._settings.max_regions]
        if not selected:
            return ()
        pair = imaging.load_pair(before, after)  # decode full pages once, not per region
        return tuple(self._analyze_region(pair, region) for region in selected)

    def _analyze_region(
        self, pair: tuple[Image.Image, Image.Image], region: Region
    ) -> RegionFinding:
        settings = self._settings
        crop_before, crop_after = imaging.crop_loaded_pair(
            pair, region, pad=settings.crop_padding, max_side=settings.crop_max_side
        )
        messages = [
            {"role": "user", "content": build_prompt(region), "images": [crop_before, crop_after]}
        ]
        attempts = settings.max_retries + 1
        last_error = ""
        for attempt in range(1, attempts + 1):
            # Same seed + temperature 0 would just repeat the same answer: vary the seed.
            options = {"temperature": settings.temperature, "seed": settings.seed + attempt - 1}
            try:
                response = self._client.chat(
                    model=settings.model,
                    messages=messages,
                    format=response_schema(),
                    options=options,
                )
            except Exception as exc:
                last_error = f"Ollama request failed: {exc}"
                logger.warning("Attempt %d/%d for region %s: %s", attempt, attempts, region, exc)
                continue
            try:
                analysis = parse_region_analysis(_content(response))
            except AIResponseError as exc:
                last_error = f"Invalid model output: {exc}"
                logger.info("Attempt %d/%d: %s", attempt, attempts, last_error)
                continue
            return RegionFinding(
                region=region, changes=normalize_changes(analysis.changes), attempts=attempt
            )
        return RegionFinding(
            region=region,
            error=f"Gave up after {attempts} attempts. {last_error}",
            attempts=attempts,
        )


def _content(response: Any) -> str:
    try:
        content = response["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise AIResponseError(f"Unexpected Ollama response shape: {exc}") from exc
    if not isinstance(content, str):
        raise AIResponseError("Ollama response content is not text")
    return content
