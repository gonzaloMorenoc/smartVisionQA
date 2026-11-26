# syntax=docker/dockerfile:1.7
# Official Playwright image: browsers live in /ms-playwright (readable by the non-root
# pwuser), so the old "browser installed for root, run as appuser" bug cannot happen.
ARG PLAYWRIGHT_VERSION=1.65.2
FROM mcr.microsoft.com/playwright/python:v${PLAYWRIGHT_VERSION}-noble

ARG PLAYWRIGHT_VERSION
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# Pin Playwright to the image version so the bundled browsers always match.
RUN pip install "playwright==${PLAYWRIGHT_VERSION}" . \
    && smartvisionqa --version

COPY demo ./demo
COPY smartvisionqa.yaml ./
# World-readable code/demo (host checkouts may be 0600) so any --user can run it.
RUN mkdir -p /app/results && chown -R pwuser:pwuser /app && chmod -R a+rX /app

USER pwuser

# Exits with the run's code (0 pass, 1 regression, 2 error): no lingering processes.
ENTRYPOINT ["smartvisionqa"]
CMD ["run", "--config", "smartvisionqa.yaml"]
