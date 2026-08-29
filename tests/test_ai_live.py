"""Live SDK check. Hits the real OpenAI API.

Runs on merge to main only, never in the PR gate — the PR job stays keyless so
that a client built at import time still fails there loudly.

This exists to catch **SDK drift**: the hand-written fake in conftest mimics the
response shape, and nothing else would notice if the real shape moved. It asserts
the call parses, not that the model plays well.
"""

import os

import pytest

from app.ai import Move, get_client, request_move
from app.engine import Board

pytestmark = [
    pytest.mark.live,
    pytest.mark.anyio,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="no OPENAI_API_KEY; live tests run on merge to main",
    ),
]


async def test_real_model_returns_a_parseable_move() -> None:
    board: Board = [["X", None, None], [None, "O", None], [None, None, None]]

    move = await request_move(get_client(), board, "X")

    assert isinstance(move, Move), "structured output failed to parse — SDK shape may have moved"
    assert isinstance(move.row, int) and isinstance(move.col, int)
    # A model that cannot pick an in-range square on a near-empty board is broken,
    # not merely playing badly. Out-of-range here is real signal, not flake.
    assert 0 <= move.row < 3 and 0 <= move.col < 3
