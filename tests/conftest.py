"""Shared fixtures.

The OpenAI double is hand-written rather than a MagicMock: it mimics the SDK
shape on purpose, so tests execute the real adapter guards instead of an
auto-created attribute chain that silently absorbs typos.
"""

from types import SimpleNamespace

import httpx2
import pytest

from app import store
from app.main import app


class FakeResponses:
    """Stands in for `client.responses`. Pops one scripted item per call."""

    def __init__(self, script: list[object]) -> None:
        self.script = script
        self.calls: list[dict] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, *script: object) -> None:
        self.responses = FakeResponses(list(script))


def response(
    output_parsed: object = None, status: str = "completed", refusal: bool = False
) -> SimpleNamespace:
    """A canned `responses.parse` result."""
    output = []
    if refusal:
        output = [SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
    return SimpleNamespace(output_parsed=output_parsed, status=status, output=output)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_store() -> object:
    """The store is module-level, so state would otherwise leak between tests."""
    store.clear()
    yield
    store.clear()


@pytest.fixture
async def client() -> object:
    """In-process HTTP client. No ports, no subprocess — the transport talks to
    the app object directly."""
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
