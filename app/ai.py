"""OpenAI-backed move selection.

The client is built per request by `get_client()` and never at import time:
`AsyncOpenAI()` raises without credentials, so an import-time client would
break keyless CI.
"""

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

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


def _render(board: list[list[str | None]]) -> str:
    return "\n".join("".join(cell or "." for cell in row) for row in board)


def _refused(resp: object) -> bool:
    for item in getattr(resp, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return True
    return False


async def request_move(
    client: AsyncOpenAI, board: list[list[str | None]], mark: str
) -> Move | None:
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
