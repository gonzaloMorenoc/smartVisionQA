"""Single source of truth for turning user-provided names (files, URLs) into safe file names."""

from __future__ import annotations

import hashlib
import re

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_HTML_EXT = re.compile(r"\.html?$", re.IGNORECASE)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_DOTS = re.compile(r"\.{2,}")
_FALLBACK = "item"
MAX_SLUG_LENGTH = 80
_HASH_LENGTH = 8


def slugify(value: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Return a filesystem-safe, deterministic slug (never contains separators or ``..``)."""
    text = _SCHEME.sub("", value.strip())
    text = _HTML_EXT.sub("", text)
    text = _UNSAFE.sub("-", text)
    text = _DOTS.sub(".", text)
    text = text.strip("-._")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    if not text:
        # Keep distinct inputs (e.g. non-ASCII names) in distinct folders.
        return _FALLBACK if not value.strip() else f"{_FALLBACK}-{digest}"
    if len(text) <= max_length:
        return text
    head = text[: max_length - _HASH_LENGTH - 1].rstrip("-._")
    return f"{head}-{digest}"


def comparison_slug(before: str, after: str) -> str:
    """Slug used for a before/after comparison folder."""
    return f"{slugify(before, 38)}__vs__{slugify(after, 38)}"
