"""Approved reference screenshots ("golden images")."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from smartvisionqa.naming import slugify


class BaselineStore:
    """Stores baselines as ``<root>/<page-slug>/<viewport-slug>.png``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, page: str, viewport: str) -> Path:
        return self._root / slugify(page) / f"{slugify(viewport)}.png"

    def load(self, page: str, viewport: str) -> bytes | None:
        path = self.path_for(page, viewport)
        return path.read_bytes() if path.is_file() else None

    def save(self, page: str, viewport: str, png: bytes) -> Path:
        """Write atomically so an interrupted run never leaves a truncated baseline."""
        path = self.path_for(page, viewport)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(png)
            Path(tmp_name).replace(path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return path
