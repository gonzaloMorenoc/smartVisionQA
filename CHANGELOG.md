# Changelog

## 1.0.0 — 2026-11-26

Complete rewrite as a tested Python package with a hybrid (pixel + AI) engine.

### Fixed
- Docker container never exited (`wait` on `ollama serve`), hanging CI jobs for hours.
- Chromium installed for root but executed as a non-root user inside Docker.
- URL comparisons crashed when writing the report (slashes in file names).
- Silent false negatives when the model wrapped its JSON or returned strings instead of lists.
- "Changes" that state nothing changed were counted as regressions.
- Greedy JSON extraction broke on trailing text with braces.
- HTML injection through file names / URLs in reports and the index.
- Process always exited 0, so CI could never fail on a regression.
- Inconsistent file naming between JSON/HTML reports, overwritten URL screenshots.
- Missing `github-pages` environment and over-broad permissions in the Pages workflow.

- (review) Error pages (HTTP 4xx/5xx) are rejected instead of being baselined.
- (review) Crashes always exit 2, never 1; evaluation exits 2 when the model fails.
- (review) Names that would share an artifact folder are rejected; non-ASCII names no longer collide.
- (review) Stale screenshots are removed before each check; credentials/query strings are
  redacted from labels; XML-invalid characters and Markdown links are neutralised in reports.

### Added
- Deterministic pixel diff with region clustering as the pass/fail oracle.
- Per-region AI explanations with Ollama structured outputs, temperature 0, seed, retries.
- Baselines with `--update-baselines`, multi-viewport runs, CSS masks, stable captures.
- YAML config validated by pydantic; `run`, `compare`, `evaluate` commands; exit codes.
- Reports: HTML (Jinja2 autoescape + CSP), index, JUnit XML, Markdown job summary, JSON.
- Evaluation suite with controlled mutations and precision/recall/F1 metrics.
- 150+ tests (unit, property-based, browser integration, e2e) with an 80 % coverage gate.
- CI: ruff, mypy strict, bandit, pip-audit, hadolint, actionlint, Docker smoke test,
  Python 3.10–3.13 matrix; Dependabot; pre-commit.
- Docker image on the official Playwright base, non-root; docker compose with Ollama service.

### Removed
- `smartVisionQA.py`, `generate_html_report.py`, `example_url_comparison.py`,
  `scripts/generate_index.py`, `docker-entrypoint.sh`, `requirements.txt` (replaced by the
  `smartvisionqa` package and `pyproject.toml`).
