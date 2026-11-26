from __future__ import annotations

from pathlib import Path

import pytest

from smartvisionqa.config import Config, ConfigError, Viewport, load_config, parse_viewport


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "smartvisionqa.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestDefaults:
    def test_default_config_is_valid_and_deterministic(self) -> None:
        config = Config()
        assert [v.name for v in config.viewports] == ["desktop"]
        assert config.diff.max_diff_ratio == 0.0
        assert config.ai.temperature == 0.0
        assert config.ai.seed is not None
        assert config.capture.disable_animations is True

    def test_config_is_immutable(self) -> None:
        config = Config()
        with pytest.raises(Exception):  # noqa: B017 - pydantic raises ValidationError
            config.output_dir = Path("x")  # type: ignore[misc]


class TestLoadConfig:
    def test_full_config(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            """
viewports:
  - {name: mobile, width: 390, height: 844, device_scale_factor: 2}
  - {name: desktop, width: 1280, height: 800}
diff: {pixel_threshold: 0.2, max_diff_ratio: 0.001}
ai: {enabled: false, model: gemma3:4b}
pages:
  - {name: home, target: demo/page_v1.html, viewports: [mobile], mask: [".clock"]}
comparisons:
  - {name: v1-v2, before: demo/page_v1.html, after: demo/page_v2.html}
""",
        )
        config = load_config(path)
        assert config.base_dir == tmp_path.resolve()
        assert config.viewports[0].device_scale_factor == 2
        assert config.diff.max_diff_ratio == 0.001
        assert config.ai.enabled is False
        assert config.pages[0].mask == (".clock",)
        assert config.viewports_for(config.pages[0]) == (config.viewports[0],)
        assert config.viewports_for(config.comparisons[0]) == config.viewports

    def test_paths_are_relative_to_config_file(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path, "output_dir: out\nbaseline_dir: base\n"))
        assert config.resolved_output_dir == tmp_path.resolve() / "out"
        assert config.resolved_baseline_dir == tmp_path.resolve() / "base"

    def test_empty_file_gives_defaults(self, tmp_path: Path) -> None:
        assert load_config(write(tmp_path, "")).pages == ()

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "missing.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="YAML"):
            load_config(write(tmp_path, "pages: [unclosed"))

    def test_top_level_must_be_mapping(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="mapping"):
            load_config(write(tmp_path, "- a\n- b\n"))

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ("unknown_key: 1", "unknown_key"),
            ("diff: {pixel_threshold: 2}", "pixel_threshold"),
            ("viewports: [{name: a, width: 0, height: 10}]", "width"),
            ("viewports: []", "viewports"),
            (
                "viewports: [{name: a, width: 1, height: 1}, {name: a, width: 2, height: 2}]",
                "Duplicate viewport",
            ),
            (
                "pages: [{name: p, target: a.html}, {name: p, target: b.html}]",
                "Duplicate page",
            ),
            ("pages: [{name: p, target: a.html, viewports: [tablet]}]", "tablet"),
            ("comparisons: [{name: c, before: a.html}]", "after"),
            ("capture: {extra_wait_ms: -1}", "extra_wait_ms"),
        ],
    )
    def test_validation_errors_are_reported_clearly(
        self, tmp_path: Path, body: str, message: str
    ) -> None:
        with pytest.raises(ConfigError, match=message):
            load_config(write(tmp_path, body))


class TestParseViewport:
    def test_parses_width_x_height(self) -> None:
        assert parse_viewport("390x844") == Viewport(name="390x844", width=390, height=844)

    @pytest.mark.parametrize("raw", ["", "abc", "10", "0x10", "10x", "99999x10"])
    def test_rejects_garbage(self, raw: str) -> None:
        with pytest.raises(ConfigError):
            parse_viewport(raw)
