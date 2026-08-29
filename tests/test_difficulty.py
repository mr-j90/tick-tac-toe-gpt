import random

import openai
import pytest

from app.ai import BLUNDER_RATES, AIUnavailable, Move, choose_move, legal_moves
from app.engine import Board, is_legal
from tests.conftest import FakeClient, response

pytestmark = pytest.mark.anyio

BOARD: Board = [["X", None, None], [None, "O", None], [None, None, None]]


class ScriptedRandom(random.Random):
    """Returns exactly the random() values a test names, so a rate boundary can
    be pinned rather than sampled, then falls back to a fixed seed.

    The tail matters: overriding random() makes Random.choice route through it
    instead of getrandbits, so the picker consumes values too.
    """

    def __init__(self, *values: float) -> None:
        super().__init__(0)
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else super().random()


def model_says(row: int, col: int) -> FakeClient:
    return FakeClient(response(output_parsed=Move(row=row, col=col)))


@pytest.mark.parametrize(
    ("difficulty", "roll", "should_call_model"),
    [
        ("easy", 0.69, False),
        ("easy", 0.71, True),
        ("medium", 0.29, False),
        ("medium", 0.31, True),
        ("hard", 0.0, True),
        ("hard", 0.99, True),
    ],
    ids=["easy-under", "easy-over", "medium-under", "medium-over", "hard-zero", "hard-high"],
)
async def test_blunder_rate_decides_whether_the_model_is_asked(
    difficulty: str, roll: float, should_call_model: bool
) -> None:
    client = model_says(0, 1)
    rng = ScriptedRandom(roll)

    move = await choose_move(client, rng, BOARD, "O", difficulty)

    assert bool(client.responses.calls) is should_call_model
    assert is_legal(BOARD, move.row, move.col)


async def test_hard_never_blunders() -> None:
    """0.0 must mean never, not almost never: random() returns [0.0, 1.0)."""
    assert BLUNDER_RATES["hard"] == 0.0
    client = model_says(0, 1)
    move = await choose_move(client, ScriptedRandom(0.0), BOARD, "O", "hard")
    assert client.responses.calls, "hard must always consult the model"
    assert move == Move(row=0, col=1)


async def test_a_blunder_never_calls_the_model_at_all() -> None:
    client = FakeClient()  # empty script: any call to the model raises IndexError
    move = await choose_move(client, ScriptedRandom(0.0), BOARD, "O", "easy")
    assert is_legal(BOARD, move.row, move.col)


@pytest.mark.parametrize(
    "bad",
    [
        response(output_parsed=Move(row=0, col=0)),  # occupied square
        response(output_parsed=Move(row=9, col=9)),  # off the board
        response(output_parsed=None),  # unparseable
        response(refusal=True),  # refusal
        response(output_parsed=Move(row=0, col=1), status="incomplete"),
    ],
    ids=["occupied", "off-board", "unparseable", "refusal", "incomplete"],
)
async def test_every_model_level_failure_falls_back_to_a_legal_move(bad: object) -> None:
    client = FakeClient(bad)
    move = await choose_move(client, ScriptedRandom(1.0), BOARD, "O", "hard")

    assert move in legal_moves(BOARD)
    assert is_legal(BOARD, move.row, move.col)
    assert len(client.responses.calls) == 1, "no retry: the human is blocked on this request"


async def test_transport_failure_is_not_absorbed() -> None:
    client = FakeClient(openai.APITimeoutError(request=None))
    with pytest.raises(AIUnavailable):
        await choose_move(client, ScriptedRandom(1.0), BOARD, "O", "hard")


async def test_a_seeded_rng_pins_exactly_which_move_is_blundered() -> None:
    first = await choose_move(model_says(0, 1), random.Random(1234), BOARD, "O", "easy")
    again = await choose_move(model_says(0, 1), random.Random(1234), BOARD, "O", "easy")
    other = await choose_move(model_says(0, 1), random.Random(9999), BOARD, "O", "easy")

    assert first == again, "same seed must give the same move"
    assert first in legal_moves(BOARD)
    assert other in legal_moves(BOARD)


async def test_blunders_only_ever_pick_empty_squares() -> None:
    board: Board = [["X", "O", "X"], ["O", "X", None], ["O", None, "O"]]
    for seed in range(50):
        move = await choose_move(model_says(0, 1), random.Random(seed), board, "O", "easy")
        assert board[move.row][move.col] is None
