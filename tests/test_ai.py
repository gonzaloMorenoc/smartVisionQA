from __future__ import annotations

import json
from typing import Any

import pytest

from smartvisionqa.ai.analyzer import VisionAnalyzer
from smartvisionqa.ai.parsing import AIResponseError, parse_region_analysis
from smartvisionqa.ai.prompt import build_prompt
from smartvisionqa.ai.schema import (
    Category,
    Change,
    Severity,
    is_noop,
    max_severity,
    normalize_changes,
    response_schema,
)
from smartvisionqa.config import AISettings
from smartvisionqa.diff import Region
from tests.conftest import make_png

REGION = Region(x=10, y=10, width=40, height=20)


def change(**overrides: Any) -> Change:
    data: dict[str, Any] = {"category": "text", "description": "Title changed"}
    data.update(overrides)
    return Change.model_validate(data)


class TestNoopFilter:
    @pytest.mark.parametrize(
        "description",
        [
            "No changes",
            "none",
            "N/A",
            "No visible differences.",
            "The pages are identical",
            "V1 has '98%' as the accuracy, V2 has '98%' as the accuracy",
            "V1 has a red button, V2 has a red button",
        ],
    )
    def test_noops_are_detected(self, description: str) -> None:
        assert is_noop(change(description=description))

    def test_equal_before_after_alone_is_not_a_noop(self) -> None:
        assert not is_noop(change(description="Price moved down", before="10 €", after="10 €"))

    @pytest.mark.parametrize(
        "description",
        [
            "V1 has '95%' accuracy, V2 has '98%' accuracy",
            "Button text changed from 'Get Started' to 'Start Free Trial'",
            "No border on the card anymore; a shadow was added",
        ],
    )
    def test_real_changes_are_kept(self, description: str) -> None:
        assert not is_noop(change(description=description))

    def test_normalize_drops_noops_and_duplicates(self) -> None:
        changes = [
            change(description="Title changed"),
            change(description="title changed "),
            change(description="No changes"),
            change(category="style", description="Title changed"),
        ]
        result = normalize_changes(changes)
        assert [(c.category, c.description) for c in result] == [
            (Category.TEXT, "Title changed"),
            (Category.STYLE, "Title changed"),
        ]


class TestSchema:
    def test_change_is_immutable_and_validated(self) -> None:
        item = change()
        with pytest.raises(Exception):  # noqa: B017
            item.description = "x"  # type: ignore[misc]
        assert change(confidence=3).confidence == pytest.approx(0.03)
        assert change(confidence=250).confidence == 1.0
        with pytest.raises(Exception):  # noqa: B017
            change(confidence="very")

    def test_enum_members_are_accepted_as_is(self) -> None:
        item = Change(category=Category.STYLE, description="x", severity=Severity.HIGH)
        assert (item.category, item.severity) == (Category.STYLE, Severity.HIGH)

    def test_schema_lists_categories(self) -> None:
        schema = response_schema()
        assert "changes" in schema["properties"]
        assert "layout" in json.dumps(schema)

    def test_max_severity(self) -> None:
        assert max_severity([]) is None
        assert max_severity([change(severity="low"), change(severity="high")]) is Severity.HIGH


class TestParsing:
    def test_structured_response(self) -> None:
        raw = json.dumps({"changes": [{"category": "style", "description": "Button is blue"}]})
        assert parse_region_analysis(raw).changes[0].category is Category.STYLE

    def test_code_fences_are_stripped(self) -> None:
        raw = '```json\n{"changes": [{"category": "text", "description": "Title"}]}\n```'
        assert len(parse_region_analysis(raw).changes) == 1

    def test_wrapped_in_differences_is_not_a_silent_false_negative(self) -> None:
        raw = json.dumps({"differences": {"layout_changes": ["Sidebar removed"]}})
        result = parse_region_analysis(raw)
        assert [(c.category, c.description) for c in result.changes] == [
            (Category.LAYOUT, "Sidebar removed")
        ]

    def test_legacy_format_with_objects_strings_and_scalars(self) -> None:
        raw = json.dumps(
            {
                "layout_changes": [{"description": "Header moved"}],
                "text_changes": "Title changed",
                "style_changes": [],
                "element_changes": ["New badge"],
            }
        )
        descriptions = sorted(c.description for c in parse_region_analysis(raw).changes)
        assert descriptions == ["Header moved", "New badge", "Title changed"]

    def test_json_followed_by_text_with_braces(self) -> None:
        raw = 'Here: {"changes": []} note {x}'
        assert parse_region_analysis(raw).changes == ()

    def test_unknown_category_falls_back_to_element(self) -> None:
        raw = json.dumps({"changes": [{"category": "colour", "description": "Blue now"}]})
        assert parse_region_analysis(raw).changes[0].category is Category.ELEMENT

    @pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", '{"foo": 1}', '{"changes": 3}'])
    def test_garbage_raises(self, raw: str) -> None:
        with pytest.raises(AIResponseError):
            parse_region_analysis(raw)


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return {"message": {"content": response}}

    def show(self, model: str) -> dict[str, Any]:
        if model == "missing":
            raise RuntimeError("model 'missing' not found")
        return {"model": model}


def ok_response(*descriptions: str) -> str:
    return json.dumps(
        {
            "changes": [
                {"category": "text", "description": d, "severity": "high"} for d in descriptions
            ]
        }
    )


class TestVisionAnalyzer:
    def test_sends_two_labelled_images_with_deterministic_options(self) -> None:
        client = FakeClient([ok_response("Title changed")])
        analyzer = VisionAnalyzer(AISettings(seed=7), client=client)
        findings = analyzer.analyze(
            make_png(), make_png(rects=[(10, 10, 5, 5, (0, 0, 0))]), [REGION]
        )
        call = client.calls[0]
        assert call["options"] == {"temperature": 0.0, "seed": 7}  # first attempt
        assert call["format"] == response_schema()
        assert len(call["messages"][0]["images"]) == 2
        assert "BEFORE" in call["messages"][0]["content"]
        assert findings[0].region == REGION
        assert findings[0].changes[0].description == "Title changed"
        assert findings[0].error is None

    def test_retries_on_invalid_output_then_succeeds(self) -> None:
        client = FakeClient(["garbage", ok_response("ok")])
        analyzer = VisionAnalyzer(AISettings(max_retries=1), client=client)
        findings = analyzer.analyze(make_png(), make_png(), [REGION])
        assert len(client.calls) == 2
        assert findings[0].changes[0].description == "ok"

    def test_gives_up_after_retries_and_records_error(self) -> None:
        client = FakeClient(["garbage", "still garbage"])
        analyzer = VisionAnalyzer(AISettings(max_retries=1), client=client)
        finding = analyzer.analyze(make_png(), make_png(), [REGION])[0]
        assert finding.changes == ()
        assert finding.error is not None
        assert "invalid" in finding.error.lower()

    def test_transport_error_is_recorded_not_raised(self) -> None:
        client = FakeClient([ConnectionError("connection refused")])
        finding = VisionAnalyzer(AISettings(max_retries=0), client=client).analyze(
            make_png(), make_png(), [REGION]
        )[0]
        assert finding.error is not None
        assert "connection refused" in finding.error

    def test_noop_changes_from_model_are_filtered(self) -> None:
        client = FakeClient([ok_response("No changes", "V1 has 'A', V2 has 'A'")])
        finding = VisionAnalyzer(AISettings(), client=client).analyze(
            make_png(), make_png(), [REGION]
        )[0]
        assert finding.changes == ()

    def test_only_top_regions_are_analysed(self) -> None:
        regions = [Region(x=i, y=0, width=5, height=5) for i in range(5)]
        client = FakeClient([ok_response("x")] * 5)
        findings = VisionAnalyzer(AISettings(max_regions=2), client=client).analyze(
            make_png(), make_png(), regions
        )
        assert len(findings) == 2
        assert len(client.calls) == 2

    def test_check_available(self) -> None:
        assert VisionAnalyzer(AISettings(), client=FakeClient([])).check_available() is None
        problem = VisionAnalyzer(
            AISettings(model="missing"), client=FakeClient([])
        ).check_available()
        assert problem is not None
        assert "missing" in problem

    def test_prompt_mentions_region_and_rules(self) -> None:
        prompt = build_prompt(REGION)
        assert "x=10" in prompt
        assert "Never report" in prompt
