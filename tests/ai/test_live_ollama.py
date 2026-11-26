"""Opt-in: talks to a real Ollama server (pytest -m ai). Skipped when it is not reachable."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from smartvisionqa.ai.analyzer import VisionAnalyzer
from smartvisionqa.ai.schema import Category
from smartvisionqa.capture import CaptureRequest, PlaywrightCapturer
from smartvisionqa.config import AISettings, CaptureSettings, DiffSettings, Viewport
from smartvisionqa.diff import compare_images
from smartvisionqa.targets import resolve_target

pytestmark = pytest.mark.ai

DEMO = Path(__file__).resolve().parents[2] / "demo"
MODEL = os.environ.get("SVQA_MODEL", "qwen2.5vl:7b")


@pytest.fixture(scope="module")
def analyzer() -> VisionAnalyzer:
    instance = VisionAnalyzer(AISettings(model=MODEL, timeout_s=600))
    problem = instance.check_available()
    if problem:
        pytest.skip(problem)
    return instance


def test_model_explains_a_text_change(analyzer: VisionAnalyzer) -> None:
    target = resolve_target("page_v1.html", DEMO)
    viewport = Viewport(name="desktop", width=1280, height=800)
    script = "() => { document.querySelector('.button').textContent = 'Start Free Trial'; }"
    with PlaywrightCapturer(CaptureSettings()) as capturer:
        before = capturer.capture(CaptureRequest(target=target, viewport=viewport))
        after = capturer.capture(CaptureRequest(target=target, viewport=viewport, script=script))
    diff = compare_images(before, after, DiffSettings())
    findings = analyzer.analyze(before, after, diff.regions)
    assert all(finding.error is None for finding in findings)
    categories = {change.category for finding in findings for change in finding.changes}
    assert Category.TEXT in categories or Category.ELEMENT in categories
