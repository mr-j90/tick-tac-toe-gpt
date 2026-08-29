import httpx2
import openai
import pytest

from app.ai import MODEL, AIUnavailable, Move, request_move
from app.engine import Board
from tests.conftest import FakeClient, response

pytestmark = pytest.mark.anyio

BOARD: Board = [["X", None, None], [None, "O", None], [None, None, None]]


async def test_returns_parsed_move() -> None:
    client = FakeClient(response(output_parsed=Move(row=0, col=1)))
    assert await request_move(client, BOARD, "O") == Move(row=0, col=1)


async def test_pins_the_model_and_renders_the_board() -> None:
    client = FakeClient(response(output_parsed=Move(row=0, col=1)))
    await request_move(client, BOARD, "O")
    call = client.responses.calls[0]
    assert call["model"] == MODEL == "gpt-5.6-luna"
    assert "X..\n.O.\n..." in call["input"]


async def test_incomplete_returns_none() -> None:
    client = FakeClient(response(output_parsed=Move(row=0, col=1), status="incomplete"))
    assert await request_move(client, BOARD, "O") is None


async def test_refusal_returns_none() -> None:
    client = FakeClient(response(refusal=True))
    assert await request_move(client, BOARD, "O") is None


async def test_unparseable_returns_none() -> None:
    client = FakeClient(response(output_parsed=None))
    assert await request_move(client, BOARD, "O") is None


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=_request())


@pytest.mark.parametrize(
    "exc",
    [
        openai.APITimeoutError(request=_request()),
        openai.APIConnectionError(message="boom", request=_request()),
        openai.RateLimitError("slow down", response=_response(429), body=None),
        openai.APIStatusError("server error", response=_response(500), body=None),
    ],
    ids=["timeout", "connection", "rate_limit", "status"],
)
async def test_transport_errors_raise_ai_unavailable(exc: Exception) -> None:
    client = FakeClient(exc)
    with pytest.raises(AIUnavailable):
        await request_move(client, BOARD, "O")


def test_no_client_constructed_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keyless CI depends on this: AsyncOpenAI() raises without credentials."""
    import importlib
    import sys

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sys.modules.pop("app.ai", None)
    importlib.import_module("app.ai")
