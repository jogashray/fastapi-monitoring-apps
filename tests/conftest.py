"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# Reduce environment poll during tests
os.environ.setdefault("SYSTEM_METRICS_INTERVAL", "60")
os.environ.setdefault("MAX_DATA_ITEMS", "100")

# Import the FastAPI app — must happen after env tweaks
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole session — required by ASGI in-process tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """In-process AsyncClient bound to the FastAPI ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # The lifespan context is started by httpx entering the app
        yield ac
