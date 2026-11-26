from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from smartvisionqa.naming import comparison_slug, slugify
from smartvisionqa.targets import Target, TargetError, resolve_target


class TestSlugify:
    def test_html_file_drops_extension_and_keeps_parent(self) -> None:
        assert slugify("demo/page_v1.html") == "demo-page_v1"

    def test_url_drops_scheme_and_unsafe_chars(self) -> None:
        assert slugify("https://example.com/a/b?q=1") == "example.com-a-b-q-1"

    def test_no_path_separators_ever(self) -> None:
        assert "/" not in slugify("https://example.com/../../etc/passwd")
        assert ".." not in slugify("../../etc/passwd")

    def test_empty_falls_back(self) -> None:
        assert slugify("") == "item"
        assert slugify("///").startswith("item-")

    def test_long_values_are_truncated_with_stable_hash(self) -> None:
        a = slugify("https://example.com/" + "a" * 300)
        b = slugify("https://example.com/" + "a" * 299 + "b")
        assert len(a) <= 80
        assert a != b
        assert a == slugify("https://example.com/" + "a" * 300)

    @given(st.text())
    def test_property_always_filesystem_safe(self, value: str) -> None:
        result = slugify(value)
        assert result
        assert "/" not in result
        assert "\\" not in result
        assert not result.startswith(".")
        assert len(result) <= 80

    def test_comparison_slug(self) -> None:
        assert comparison_slug("page_v1.html", "page_v2.html") == "page_v1__vs__page_v2"


class TestResolveTarget:
    def test_http_url(self, tmp_path: Path) -> None:
        target = resolve_target("https://example.com", tmp_path)
        assert target == Target(
            kind="url", location="https://example.com", label="https://example.com"
        )

    def test_relative_file_is_resolved_against_base_dir(self, tmp_path: Path) -> None:
        page = tmp_path / "my page.html"
        page.write_text("<html></html>")
        target = resolve_target("my page.html", tmp_path)
        assert target.kind == "file"
        assert target.location == page.resolve().as_uri()
        assert "%20" in target.location
        assert target.label == "my page.html"

    def test_file_uri_is_accepted(self, tmp_path: Path) -> None:
        page = tmp_path / "p.html"
        page.write_text("x")
        assert resolve_target(page.as_uri(), tmp_path).kind == "file"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TargetError, match="not found"):
            resolve_target("nope.html", tmp_path)

    def test_directory_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TargetError, match="not a file"):
            resolve_target(".", tmp_path)

    @pytest.mark.parametrize("raw", ["javascript:alert(1)", "ftp://x.org/f", "data:text/html,hi"])
    def test_unsupported_schemes_are_rejected(self, raw: str, tmp_path: Path) -> None:
        with pytest.raises(TargetError, match="Unsupported"):
            resolve_target(raw, tmp_path)

    def test_url_without_host_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TargetError, match="host"):
            resolve_target("https://", tmp_path)

    def test_blank_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TargetError, match="empty"):
            resolve_target("   ", tmp_path)
