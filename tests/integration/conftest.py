"""Fixtures shared by browser-backed integration tests."""

from __future__ import annotations

import functools
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[2] / "demo"


@pytest.fixture(scope="module")
def demo_server() -> Iterator[str]:
    """Serve demo/ over HTTP so URL targets are tested without the internet."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DEMO))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
