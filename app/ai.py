"""OpenAI-backed move selection.

The client is built per request by `get_client()` and never at import time:
`AsyncOpenAI()` raises without credentials, so an import-time client would
break keyless CI.
"""

import random

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.engine import Board, is_legal
from app.store import Difficulty

# Pinned exactly. The bare `gpt-5.6` is an alias for `gpt-5.6-sol`, a different model.
MODEL = "gpt-5.6-luna"
TIMEOUT_S = 10.0
MAX_RETRIES = 1

PROMPT = (
    "You are playing tic-tac-toe. The board is 3x3, rows and columns indexed 0-2. "
    "'X' and 'O' are taken squares, '.' is empty. "
    "Reply with the row and col of your next move. Play well.\n\n"
    "You are '{mark}'. Board:\n{board}"
)


class Move(BaseModel):
    """All fields required — strict schemas forbid optional fields."""

    row: int
    col: int


class AIUnavailable(Exception):
    """Transport-level failure. The caller maps this to 502 ai_unavailable."""


def get_client() -> AsyncOpenAI:
    """FastAPI dependency. Async so the model call does not block the event loop."""
    return AsyncOpenAI(timeout=TIMEOUT_S, max_retries=MAX_RETRIES)


def _render(board: Board) -> str:
    return "\n".join("".join(cell or "." for cell in row) for row in board)


def _refused(resp: object) -> bool:
    for item in getattr(resp, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return True
    return False


async def request_move(client: AsyncOpenAI, board: Board, mark: str) -> Move | None:
    """Ask the model for a move.

    Returns None on any model-level failure — refusal, incomplete, or an
    unparseable response. The caller falls back to a random legal move; there
    is deliberately no retry, since the human is blocked on this request and
    TIMEOUT_S already bounds it.

    Raises AIUnavailable on transport failure.
    """
    try:
        resp = await client.responses.parse(
            model=MODEL,
            input=PROMPT.format(mark=mark, board=_render(board)),
            text_format=Move,
        )
    except openai.APIError as exc:
        # APITimeoutError, RateLimitError, APIConnectionError and APIStatusError
        # all descend from APIError.
        raise AIUnavailable(str(exc)) from exc

    if getattr(resp, "status", None) == "incomplete":
        return None
    if _refused(resp):
        return None
    return resp.output_parsed


# Difficulty is a blunder rate, not a prompt variation: a model asked to play
# badly is unreliable, and no test can assert a level differs without asserting
# on model behaviour. A probability is a dial tests can pin exactly.
BLUNDER_RATES: dict[Difficulty, float] = {"easy": 0.7, "medium": 0.3, "hard": 0.0}


def get_rng() -> random.Random:
    """FastAPI dependency, overridden in tests with a seeded instance."""
    return random.Random()


def legal_moves(board: Board) -> list[Move]:
    return [
        Move(row=r, col=c)
        for r in range(len(board))
        for c in range(len(board[r]))
        if board[r][c] is None
    ]


def random_legal_move(board: Board, rng: random.Random) -> Move:
    """Precondition: the board has an empty square. The caller only reaches
    here while the game is in progress, and a full board is never in progress."""
    return rng.choice(legal_moves(board))


async def choose_move(
    client: AsyncOpenAI,
    rng: random.Random,
    board: Board,
    mark: str,
    difficulty: Difficulty,
) -> Move:
    """The AI's move for one turn.

    Blunders with the level's probability; otherwise asks the model. Any
    model-level failure — refusal, incomplete, unparseable, or a move that is
    not legal — falls through to the same random picker, with no retry.

    Raises AIUnavailable if the transport failed; that is not absorbed, because
    a silently random opponent while OpenAI is down is worse than an error.
    """
    if rng.random() < BLUNDER_RATES[difficulty]:
        return random_legal_move(board, rng)

    move = await request_move(client, board, mark)
    if move is None or not is_legal(board, move.row, move.col):
        return random_legal_move(board, rng)
    return move
