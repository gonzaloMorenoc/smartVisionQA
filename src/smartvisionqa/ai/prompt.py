"""Prompt for explaining one changed region."""

from __future__ import annotations

from smartvisionqa.diff import Region

_TEMPLATE = """You are a meticulous visual QA engineer reviewing a web page regression.

Image 1 is the BEFORE (approved baseline) crop and Image 2 is the AFTER (candidate) crop of
the SAME region of the page (page coordinates x={x}, y={y}, size {w}x{h}px). A pixel diff has
already proven that this region changed; your job is to explain HOW.

List every concrete visual difference between BEFORE and AFTER:
- category "layout": position, size, spacing, alignment, order of elements
- category "text": wording, numbers, labels, missing or added copy
- category "style": colours, fonts, borders, shadows, backgrounds, icons styling
- category "element": a component (button, badge, banner, image, card) added, removed or replaced
Fill "before" and "after" with the exact visible values when you can read them.
severity: "high" if it affects primary content, calls to action, prices, legal text or
readability; "medium" for clearly noticeable cosmetic changes; "low" for subtle ones.
confidence: how sure you are, from 0 to 1.

Rules:
- Never report something that looks the same in both images.
- Do not guess about content outside the crops.
- If the only difference is anti-aliasing or sub-pixel rendering, return an empty list.
Respond only with JSON that matches the provided schema."""


def build_prompt(region: Region) -> str:
    return _TEMPLATE.format(x=region.x, y=region.y, w=region.width, h=region.height)
