"""Validation of capture targets (local HTML files or http(s) URLs)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import ParseResult, unquote, urlparse, urlunparse

_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


class TargetError(ValueError):
    """Raised when a target cannot be captured safely."""


@dataclass(frozen=True)
class Target:
    """A validated location Playwright can navigate to."""

    kind: Literal["url", "file"]
    location: str
    label: str


def resolve_target(raw: str, base_dir: Path) -> Target:
    """Validate ``raw`` and turn it into a navigable :class:`Target`.

    Relative file paths are resolved against ``base_dir``. Only http(s) and existing local
    files are accepted, so configs cannot smuggle ``javascript:`` or ``data:`` URLs.
    """
    value = raw.strip()
    if not value:
        raise TargetError("Target is empty")

    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme in _ALLOWED_URL_SCHEMES:
        if not parsed.hostname:
            raise TargetError(f"URL has no host: {value!r}")
        return Target(kind="url", location=value, label=_redact(parsed))
    if scheme == "file":
        return _file_target(Path(unquote(parsed.path)), label=value)
    if len(scheme) > 1:  # single letters are Windows drive letters
        raise TargetError(
            f"Unsupported target scheme {scheme!r} in {value!r} "
            "(URLs must start with http:// or https://; files need an existing path)"
        )
    path = Path(value)
    return _file_target(path if path.is_absolute() else base_dir / path, label=value)


def display_label(raw: str) -> str:
    """Publishable label for any raw target string (URLs lose credentials and query)."""
    value = raw.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() in _ALLOWED_URL_SCHEMES and parsed.hostname:
        return _redact(parsed)
    return value


def _redact(parsed: ParseResult) -> str:
    """Label safe to publish in reports: no user:password, query string or fragment."""
    host = parsed.hostname or ""
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    label = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
    return f"{label}?…" if parsed.query else label


def _file_target(path: Path, label: str) -> Target:
    resolved = path.resolve()
    if not resolved.exists():
        raise TargetError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise TargetError(f"Target is not a file: {resolved}")
    return Target(kind="file", location=resolved.as_uri(), label=label)
