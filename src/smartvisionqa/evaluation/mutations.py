"""Controlled visual mutations with known ground truth (targeting demo/page_v1.html)."""

from __future__ import annotations

from dataclasses import dataclass

from smartvisionqa.ai.schema import Category


@dataclass(frozen=True)
class Mutation:
    id: str
    category: Category | None  # None = control case: nothing should be detected
    description: str
    script: str


def _on(selector: str, body: str) -> str:
    """Build a script that fails loudly if the selector disappears from the page."""
    return (
        "() => { const el = document.querySelector(" + repr(selector) + "); "
        "if (!el) { throw new Error('selector not found: ' + "
        + repr(selector)
        + "); } "
        + body
        + " }"
    )


DEFAULT_MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "text-title",
        Category.TEXT,
        "Main title wording changes",
        _on("h1", "el.textContent = 'SmartVision QA Platinum';"),
    ),
    Mutation(
        "text-stat",
        Category.TEXT,
        "First statistic changes from 95% to 98%",
        _on(".stat-number", "el.textContent = '98%';"),
    ),
    Mutation(
        "text-button",
        Category.TEXT,
        "Call-to-action label changes",
        _on(".button", "el.textContent = 'Start Free Trial';"),
    ),
    Mutation(
        "style-title-color",
        Category.STYLE,
        "Title colour turns red",
        _on("h1", "el.style.color = '#dc2626';"),
    ),
    Mutation(
        "style-button-bg",
        Category.STYLE,
        "Button background turns green",
        _on(".button", "el.style.background = '#16a34a'; el.style.color = '#ffffff';"),
    ),
    Mutation(
        "style-card-outline",
        Category.STYLE,
        "First feature card gets an orange outline",
        _on(".feature-card", "el.style.outline = '4px solid #f97316';"),
    ),
    Mutation(
        "layout-card-shift",
        Category.LAYOUT,
        "First feature card moves down",
        _on(".feature-card", "el.style.position = 'relative'; el.style.top = '40px';"),
    ),
    Mutation(
        "layout-header-align",
        Category.LAYOUT,
        "Header content becomes centred",
        _on("header", "el.style.textAlign = 'center';"),
    ),
    Mutation(
        "element-hide-button",
        Category.ELEMENT,
        "Call-to-action button disappears",
        _on(".button", "el.style.visibility = 'hidden';"),
    ),
    Mutation(
        "element-add-badge",
        Category.ELEMENT,
        "A 'BETA' badge is added to the header",
        _on(
            "header",
            "el.style.position = 'relative'; const b = document.createElement('span'); "
            "b.textContent = 'BETA'; b.style.cssText = 'position:absolute;top:8px;right:8px;"
            "background:#f59e0b;color:#111;padding:4px 10px;border-radius:999px;font:700 14px "
            "sans-serif'; el.appendChild(b);",
        ),
    ),
    Mutation(
        "control-noop", None, "No change at all (must not be flagged)", "() => { /* noop */ }"
    ),
)
