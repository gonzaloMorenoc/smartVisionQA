"""JUnit XML so any CI (GitHub, GitLab, Jenkins) shows visual checks as test results."""

from __future__ import annotations

import re

# Only *writing* XML from our own data; nothing untrusted is parsed here.
import xml.etree.ElementTree as ET  # nosec B405

from smartvisionqa.report.presentation import headline, percent
from smartvisionqa.runner import Outcome, RunSummary, Verdict

_SUITE = "smartvisionqa"
# Characters that are illegal in XML 1.0 (model or page text may contain them).
_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _xml(text: str | None) -> str:
    return _XML_INVALID.sub("", text or "")


def render_junit(summary: RunSummary) -> str:
    counts = summary.counts
    failures = counts[Verdict.FAILED.value] + counts[Verdict.MISSING_BASELINE.value]
    attrs = {
        "name": _SUITE,
        "tests": str(len(summary.outcomes)),
        "failures": str(failures),
        "errors": str(counts[Verdict.ERROR.value]),
        "skipped": "0",
        "time": f"{summary.duration_s:.3f}",
    }
    root = ET.Element("testsuites", attrs)
    suite = ET.SubElement(root, "testsuite", {**attrs, "timestamp": summary.started_at})
    for outcome in summary.outcomes:
        _testcase(suite, outcome)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _testcase(suite: ET.Element, outcome: Outcome) -> None:
    case = ET.SubElement(
        suite,
        "testcase",
        {
            "classname": f"{_SUITE}.{outcome.kind}",
            "name": outcome.test_id,
            "time": f"{outcome.duration_s:.3f}",
        },
    )
    if outcome.verdict is Verdict.ERROR:
        message = _xml(outcome.error) or "error"
        error = ET.SubElement(case, "error", {"message": message, "type": "error"})
        error.text = message
    elif outcome.verdict in (Verdict.FAILED, Verdict.MISSING_BASELINE):
        failure = ET.SubElement(
            case,
            "failure",
            {
                "message": _xml(headline(outcome)) or outcome.verdict.value,
                "type": outcome.verdict.value,
            },
        )
        failure.text = _xml(_details(outcome))
    ET.SubElement(case, "system-out").text = _xml(f"Artifacts: {outcome.artifact_dir}")


def _details(outcome: Outcome) -> str:
    lines = [f"{outcome.before_label} -> {outcome.after_label}"]
    if outcome.diff:
        lines.append(
            f"Changed: {percent(outcome.diff.diff_ratio)} in {len(outcome.diff.regions)} region(s)"
        )
    if outcome.error:
        lines.append(outcome.error)
    lines.extend(
        f"- [{c.category.value}/{c.severity.value}] {c.description}" for c in outcome.changes
    )
    return "\n".join(lines)
