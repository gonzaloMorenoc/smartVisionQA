# Architecture

```
src/smartvisionqa/
├── cli.py              argparse entry point, exit codes, GitHub job summary
├── config.py           pydantic models (frozen, extra="forbid") + YAML loading
├── targets.py          validation of files / http(s) URLs (rejects javascript:, data:, ...)
├── naming.py           the only place that turns names into file names (no path traversal)
├── capture.py          Playwright: one browser, one context per capture, frozen animations
├── imaging.py          safe decoding (size limits), padding, cropping, PNG encoding
├── diff.py             pixel diff + region clustering  ← decides pass/fail
├── baseline.py         golden images, atomic writes
├── runner.py           orchestration, verdicts, artifacts (result.json per check)
├── ai/
│   ├── schema.py       Change / RegionAnalysis contract, no-op filter, severities
│   ├── prompt.py       per-region prompt
│   ├── parsing.py      tolerant but explicit parsing (never "silently no changes")
│   └── analyzer.py     Ollama client: structured outputs, temperature 0, seed, retries
├── report/             Jinja2 HTML (autoescape + CSP), JUnit XML, Markdown, JSON
└── evaluation/         known mutations, metrics (recall, FPR, per-category P/R/F1)
```

## Decisions

1. **The pixel diff is the oracle.** It is deterministic and cheap. The model is only asked
   about regions that are proven different, which removes the main source of false positives
   (hallucinated changes on identical pages) and makes runs fast when nothing changed.
2. **Two crops per region instead of one stacked full-page image.** Full-page screenshots
   stacked vertically are downscaled heavily by vision models and give no clue where V1 ends.
   Crops keep detail and give the model a single, local question.
3. **Structured outputs + validation.** The JSON schema of `RegionAnalysis` is passed to Ollama
   (`format=`). Output is validated with pydantic, retried on failure, and legacy shapes are
   converted explicitly. Anything unparseable becomes an error in the report, never an empty
   "no changes" result.
4. **Graceful degradation.** If Ollama is down the run still fails/passes on pixels and the
   report says why there are no explanations.
5. **Measured AI.** `evaluate` turns "this model seems better" into numbers that CI can track.
6. **Determinism of captures.** Fixed viewport and device scale factor, `reduced_motion`,
   frozen CSS animations/transitions, hidden caret, `document.fonts.ready`, fixed locale and
   timezone, and CSS-selector masks for dynamic content.

## Verdicts

| Verdict | Meaning | Exit code contribution |
| --- | --- | --- |
| `passed` | No significant pixel change | 0 |
| `failed` | Significant change (explained by the model when available) | 1 |
| `missing_baseline` | Page has no approved baseline yet | 1 |
| `baseline_updated` | `--update-baselines` stored a new baseline | 0 |
| `error` | Target invalid, capture failed, unreadable image | 2 (wins over 1) |
