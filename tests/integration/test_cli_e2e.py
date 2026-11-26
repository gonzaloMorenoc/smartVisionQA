"""End-to-end: the real CLI with a real browser (no AI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from smartvisionqa import cli
from tests.integration.conftest import DEMO

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(("after", "expected"), [("page_v1.html", 0), ("page_v2.html", 1)])
def test_cli_end_to_end(tmp_path: Path, after: str, expected: int) -> None:
    code = cli.main(
        [
            "compare",
            str(DEMO / "page_v1.html"),
            str(DEMO / after),
            "--no-ai",
            "--output",
            str(tmp_path),
            "--name",
            "e2e",
        ]
    )
    assert code == expected
    report = tmp_path / "comparisons" / "e2e" / "desktop" / "report.html"
    assert report.is_file()
    assert (report.parent / "after.png").is_file()


def test_cli_url_comparison_does_not_crash(tmp_path: Path, demo_server: str) -> None:
    """Regression: the old report generator crashed on URLs (slashes in file names)."""
    code = cli.main(
        [
            "compare",
            f"{demo_server}/page_v1.html",
            f"{demo_server}/page_v3.html",
            "--no-ai",
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert (tmp_path / "index.html").is_file()
