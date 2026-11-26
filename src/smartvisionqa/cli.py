"""Command line interface.

Exit codes: 0 = all checks passed, 1 = visual regression / missing baseline / evaluation
threshold missed, 2 = configuration, capture or runtime error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from smartvisionqa import __version__
from smartvisionqa.ai.analyzer import VisionAnalyzer
from smartvisionqa.capture import CaptureError, PlaywrightCapturer
from smartvisionqa.config import (
    Config,
    ConfigError,
    Viewport,
    build_config,
    load_config,
    parse_viewport,
)
from smartvisionqa.evaluation.runner import (
    EvaluationError,
    render_evaluation_markdown,
    run_evaluation,
)
from smartvisionqa.report import write_reports
from smartvisionqa.report.markdown import render_markdown
from smartvisionqa.runner import EXIT_ERROR, EXIT_OK, EXIT_REGRESSION, Runner, RunSummary
from smartvisionqa.targets import TargetError, resolve_target

logger = logging.getLogger("smartvisionqa")

DEFAULT_CONFIG = Path("smartvisionqa.yaml")
DEFAULT_EVAL_TARGET = "demo/page_v1.html"
MODEL_ENV = "SVQA_MODEL"

# Factories are module attributes so tests (and embedders) can swap them.
make_capturer = PlaywrightCapturer
make_analyzer = VisionAnalyzer


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        handler: Any = args.handler
        code: int = handler(args)
    except (ConfigError, TargetError, EvaluationError, CaptureError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # last line of defence: a crash must never look like exit 1
        logger.exception("Unexpected error")
        print(f"error: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smartvisionqa",
        description="Hybrid visual regression testing: pixel diff + local vision-model triage.",
    )
    parser.add_argument("--version", action="version", version=f"smartvisionqa {__version__}")
    parser.add_argument(
        "--log-level", default="info", choices=["debug", "info", "warning", "error"]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run every page/comparison declared in a config file")
    _common(run)
    run.add_argument("--update-baselines", action="store_true", help="Approve current captures")
    run.add_argument("--link-base", help="Public URL of the output folder (for Markdown links)")
    run.set_defaults(handler=_cmd_run)

    compare = sub.add_parser("compare", help="Compare two pages (files or URLs) directly")
    compare.add_argument("before")
    compare.add_argument("after")
    _common(compare)
    compare.add_argument("--name", help="Name of the comparison (default: derived from inputs)")
    compare.add_argument("--viewport", action="append", default=[], help="WIDTHxHEIGHT, repeatable")
    compare.add_argument("--mask", action="append", default=[], help="CSS selector to mask")
    compare.add_argument("--link-base", help="Public URL of the output folder")
    compare.set_defaults(handler=_cmd_compare)

    evaluate = sub.add_parser("evaluate", help="Score detection/classification on known mutations")
    _common(evaluate)
    evaluate.add_argument("--target", default=DEFAULT_EVAL_TARGET)
    evaluate.add_argument(
        "--viewport", default=None, help="WIDTHxHEIGHT (default: first in config)"
    )
    evaluate.add_argument("--min-detection", type=float, default=1.0)
    evaluate.add_argument("--max-fpr", type=float, default=0.0)
    evaluate.add_argument("--min-f1", type=float, default=0.0)
    evaluate.set_defaults(handler=_cmd_evaluate)
    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log-level",
        default=argparse.SUPPRESS,
        choices=["debug", "info", "warning", "error"],
        help="Also accepted after the command",
    )
    parser.add_argument("--config", type=Path, help=f"YAML config (default: {DEFAULT_CONFIG})")
    parser.add_argument("--output", type=Path, help="Output folder (overrides config)")
    parser.add_argument("--no-ai", action="store_true", help="Pixel diff only, never call Ollama")
    parser.add_argument("--model", help="Ollama vision model (overrides config)")


def _load(args: argparse.Namespace, *, required: bool) -> Config:
    path: Path | None = args.config
    if path is None and DEFAULT_CONFIG.is_file():
        path = DEFAULT_CONFIG
    if path is None:
        if required:
            raise ConfigError(f"No config given and {DEFAULT_CONFIG} not found")
        config = build_config({"base_dir": Path.cwd()})
    else:
        config = load_config(path)
    overrides: dict[str, Any] = {}
    if args.output is not None:
        overrides["output_dir"] = args.output.resolve()
    ai = config.ai.model_dump()
    model = args.model or os.environ.get(MODEL_ENV)
    if model:
        ai["model"] = model
    if args.no_ai:
        ai["enabled"] = False
    overrides["ai"] = ai
    return _with(config, **overrides)


def _with(config: Config, **updates: Any) -> Config:
    """Return a re-validated copy of ``config`` with ``updates`` applied."""
    return build_config({**config.model_dump(), **updates})


def _analyzer(config: Config) -> VisionAnalyzer | None:
    return make_analyzer(config.ai) if config.ai.enabled else None


def _execute(config: Config, update_baselines: bool, link_base: str | None) -> int:
    with make_capturer(config.capture) as capturer:
        summary = Runner(
            config, capturer, _analyzer(config), update_baselines=update_baselines
        ).run()
    paths = write_reports(summary, link_base=link_base)
    _publish_step_summary(summary, link_base)
    _log_summary(summary)
    logger.info("Open the report: %s", paths.index)
    return summary.exit_code


def _cmd_run(args: argparse.Namespace) -> int:
    config = _load(args, required=True)
    if not config.pages and not config.comparisons:
        raise ConfigError("Config declares no 'pages' or 'comparisons' to check")
    return _execute(config, args.update_baselines, args.link_base)


def _cmd_compare(args: argparse.Namespace) -> int:
    config = _load(args, required=False)
    viewports: list[Viewport] = [parse_viewport(v) for v in args.viewport] or list(config.viewports)
    name = args.name or f"{Path(args.before).name} vs {Path(args.after).name}"
    comparison = {
        "name": name,
        "before": _from_cwd(args.before),
        "after": _from_cwd(args.after),
        "mask": args.mask,
    }
    # Targets are relative to the cwd; output/baseline paths stay relative to the config.
    config = _with(
        config,
        viewports=[v.model_dump() for v in viewports],
        pages=[],
        comparisons=[comparison],
    )
    return _execute(config, update_baselines=False, link_base=args.link_base)


def _from_cwd(raw: str) -> str:
    """Anchor a command-line file path to the cwd; URLs are returned unchanged."""
    if "://" in raw or Path(raw).is_absolute():
        return raw
    return str((Path.cwd() / raw).resolve())


def _cmd_evaluate(args: argparse.Namespace) -> int:
    config = _load(args, required=False)
    target = resolve_target(args.target, Path.cwd())
    viewport = parse_viewport(args.viewport) if args.viewport else config.viewports[0]
    with make_capturer(config.capture) as capturer:
        report = run_evaluation(
            target,
            capturer,
            _analyzer(config),
            viewport,
            config.diff,
            model=config.ai.model,
        )
    output = config.resolved_output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "evaluation.json").write_text(json.dumps(report.to_dict(), indent=2), "utf-8")
    markdown = render_evaluation_markdown(report)
    (output / "evaluation.md").write_text(markdown, encoding="utf-8")
    _append_step_summary(markdown)
    metrics = report.metrics
    logger.info(
        "Detection recall %.0f%% · FPR %.0f%% · category accuracy %.0f%% · macro F1 %.2f",
        metrics.detection_recall * 100,
        metrics.false_positive_rate * 100,
        metrics.category_accuracy * 100,
        metrics.macro_f1,
    )
    failed = (
        metrics.detection_recall < args.min_detection
        or metrics.false_positive_rate > args.max_fpr
        or metrics.macro_f1 < args.min_f1
    )
    errors = [case for case in report.cases if case.error]
    if errors:
        for case in errors:
            logger.error("Evaluation case %s failed: %s", case.mutation_id, case.error)
        return EXIT_ERROR
    return EXIT_REGRESSION if failed else EXIT_OK


def _publish_step_summary(summary: RunSummary, link_base: str | None) -> None:
    _append_step_summary(render_markdown(summary, link_base=link_base))


def _append_step_summary(markdown: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with Path(target).open("a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    except OSError as exc:
        logger.warning("Cannot write GitHub step summary: %s", exc)


def _log_summary(summary: RunSummary) -> None:
    for outcome in summary.outcomes:
        logger.info("%-18s %s", outcome.verdict.value.upper(), outcome.test_id)
    logger.info("Result: %s (exit code %d)", summary.counts, summary.exit_code)
