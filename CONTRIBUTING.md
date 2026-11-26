# Contributing

1. `pip install -e ".[dev]" && python -m playwright install chromium && pre-commit install`
2. Write the test first (unit tests use synthetic PNGs and fake clients; browser tests live in
   `tests/integration`, model tests in `tests/ai` and run with `pytest -m ai --no-cov`).
3. Keep the gates green: `pytest` (coverage ≥ 80 %), `ruff check`, `ruff format --check`,
   `mypy` (strict), `bandit -c pyproject.toml -r src`.
4. Changing the prompt or default model? Attach `smartvisionqa evaluate` results before/after.
5. Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`, `perf:`.
