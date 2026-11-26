"""Typed, validated, immutable configuration loaded from YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from smartvisionqa.naming import slugify

MAX_VIEWPORT_SIDE = 7680
DEFAULT_MODEL = "qwen2.5vl:7b"
_VIEWPORT_PATTERN = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")


class ConfigError(ValueError):
    """Raised for any invalid or unreadable configuration."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Viewport(_Frozen):
    name: str = Field(min_length=1)
    width: int = Field(gt=0, le=MAX_VIEWPORT_SIDE)
    height: int = Field(gt=0, le=MAX_VIEWPORT_SIDE)
    device_scale_factor: float = Field(default=1.0, gt=0, le=4)


class CaptureSettings(_Frozen):
    full_page: bool = True
    disable_animations: bool = True
    timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    wait_for_selector: str | None = None
    extra_wait_ms: int = Field(default=0, ge=0, le=30_000)
    mask: tuple[str, ...] = ()
    mask_color: str = "#FF00FF"


class DiffSettings(_Frozen):
    pixel_threshold: float = Field(
        default=0.1, ge=0, le=1, description="Per-pixel colour distance (0-1) counted as change"
    )
    max_diff_ratio: float = Field(
        default=0.0, ge=0, le=1, description="Share of significant changed pixels tolerated"
    )
    min_region_area: int = Field(
        default=1, ge=1, description="Clusters with fewer changed pixels are treated as noise"
    )
    cell_size: int = Field(default=8, ge=1, le=64, description="Grid used to cluster regions")
    max_regions: int = Field(default=10, ge=1, le=100)


class AISettings(_Frozen):
    enabled: bool = True
    model: str = Field(default=DEFAULT_MODEL, min_length=1)
    host: str | None = None
    timeout_s: float = Field(default=180.0, gt=0, le=3_600)
    temperature: float = Field(default=0.0, ge=0, le=2)
    seed: int = 42
    max_retries: int = Field(default=2, ge=0, le=5)
    max_regions: int = Field(default=6, ge=1, le=50)
    crop_padding: int = Field(default=24, ge=0, le=512)
    crop_max_side: int = Field(default=1024, ge=128, le=4096)


class PageSpec(_Frozen):
    """A page checked against a stored baseline image."""

    name: str = Field(min_length=1)
    target: str = Field(min_length=1)
    viewports: tuple[str, ...] | None = Field(default=None, min_length=1)
    mask: tuple[str, ...] = ()


class ComparisonSpec(_Frozen):
    """Two targets compared directly with each other (before vs after)."""

    name: str = Field(min_length=1)
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)
    viewports: tuple[str, ...] | None = Field(default=None, min_length=1)
    mask: tuple[str, ...] = ()


class Config(_Frozen):
    viewports: tuple[Viewport, ...] = Field(
        default=(Viewport(name="desktop", width=1280, height=800),), min_length=1
    )
    capture: CaptureSettings = CaptureSettings()
    diff: DiffSettings = DiffSettings()
    ai: AISettings = AISettings()
    pages: tuple[PageSpec, ...] = ()
    comparisons: tuple[ComparisonSpec, ...] = ()
    baseline_dir: Path = Path("baselines")
    output_dir: Path = Path("results")
    base_dir: Path = Path()

    @model_validator(mode="after")
    def _check_references(self) -> Config:
        _ensure_unique("viewport", [v.name for v in self.viewports])
        _ensure_unique("page", [p.name for p in self.pages])
        _ensure_unique("comparison", [c.name for c in self.comparisons])
        known = {v.name for v in self.viewports}
        specs: tuple[PageSpec | ComparisonSpec, ...] = (*self.pages, *self.comparisons)
        for spec in specs:
            unknown = sorted(set(spec.viewports or ()) - known)
            if unknown:
                raise ValueError(f"{spec.name!r} references unknown viewports: {unknown}")
        return self

    def viewports_for(self, spec: PageSpec | ComparisonSpec) -> tuple[Viewport, ...]:
        if spec.viewports is None:
            return self.viewports
        return tuple(v for v in self.viewports if v.name in spec.viewports)

    @property
    def resolved_output_dir(self) -> Path:
        return _resolve(self.base_dir, self.output_dir)

    @property
    def resolved_baseline_dir(self) -> Path:
        return _resolve(self.base_dir, self.baseline_dir)


def _resolve(base: Path, path: Path) -> Path:
    return (path if path.is_absolute() else base / path).resolve()


def _ensure_unique(kind: str, names: list[str]) -> None:
    """Names must be unique, and must not map to the same artifact/baseline folder."""
    seen: set[str] = set()
    folders: dict[str, str] = {}
    for name in names:
        if name in seen:
            raise ValueError(f"Duplicate {kind} name: {name!r}")
        seen.add(name)
        folder = slugify(name).casefold()  # casefold: macOS/Windows are case-insensitive
        if folder in folders:
            raise ValueError(
                f"{kind.capitalize()} names {folders[folder]!r} and {name!r} would share the "
                "same folder; rename one of them"
            )
        folders[folder] = name


def load_config(path: Path) -> Config:
    """Read and validate a YAML config. Relative paths are relative to the file's folder."""
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"Top level of {path} must be a mapping, got {type(data).__name__}")
    return build_config({**data, "base_dir": path.parent.resolve()}, source=str(path))


def build_config(data: dict[str, Any], source: str = "<config>") -> Config:
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {source}:\n{_format(exc)}") from exc


def _format(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)


def parse_viewport(raw: str) -> Viewport:
    """Parse ``WIDTHxHEIGHT`` (e.g. ``390x844``) from the command line."""
    match = _VIEWPORT_PATTERN.match(raw)
    if not match:
        raise ConfigError(f"Viewport must look like 1280x800, got {raw!r}")
    width, height = int(match.group(1)), int(match.group(2))
    try:
        return Viewport(name=f"{width}x{height}", width=width, height=height)
    except ValidationError as exc:
        raise ConfigError(f"Invalid viewport {raw!r}:\n{_format(exc)}") from exc
