import random
import secrets
from dataclasses import replace
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from app import store
from app.ai import AIUnavailable, choose_move, get_client, get_rng
from app.engine import (
    Board,
    Mark,
    Status,
    apply_move,
    current_player,
    empty_board,
    is_legal,
    opponent,
    status,
    winner,
)
from app.store import Difficulty, Game, Mode

app = FastAPI(title="tic-tac-toe")

TOKEN_BYTES = 32


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class CreateGame(BaseModel):
    mode: Mode
    difficulty: Difficulty | None = None

    @model_validator(mode="after")
    def check_difficulty(self) -> CreateGame:
        if self.mode == "ai" and self.difficulty is None:
            raise ValueError("difficulty is required for mode 'ai'")
        if self.mode == "h2h" and self.difficulty is not None:
            raise ValueError("difficulty is not allowed for mode 'h2h'")
        return self


class GameView(BaseModel):
    """What anyone holding the game id may see. Turn, status and winner are
    derived here rather than stored, so they cannot drift from the board."""

    id: str
    board: Board
    mode: Mode
    difficulty: Difficulty | None
    current_player: Mark
    status: Status
    winner: Mark | None


class CreatedGame(GameView):
    tokens: dict[Mark, str]
    """Mark -> token, inverted from storage: the creator needs to know which
    token belongs to which side so they can hand the opponent theirs."""


def view(game: Game) -> GameView:
    return GameView(
        id=game.id,
        board=game.board,
        mode=game.mode,
        difficulty=game.difficulty,
        current_player=current_player(game.board),
        status=status(game.board),
        winner=winner(game.board),
    )


@app.post("/games", status_code=201)
def create_game(body: CreateGame) -> CreatedGame:
    marks: list[Mark] = ["X", "O"] if body.mode == "h2h" else ["X"]
    tokens = {mark: secrets.token_urlsafe(TOKEN_BYTES) for mark in marks}
    game = Game(
        id=uuid4().hex,
        board=empty_board(),
        mode=body.mode,
        difficulty=body.difficulty,
        tokens={token: mark for mark, token in tokens.items()},
    )
    store.save(game)
    return CreatedGame(**view(game).model_dump(), tokens=tokens)


@app.get("/games/{game_id}")
def read_game(game_id: str) -> GameView:
    """Public. The unguessable id is the capability; a token proves which side
    you play, not whether you may look."""
    game = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="unknown_game")
    return view(game)


class MoveIn(BaseModel):
    """Range is enforced here so an out-of-board move is Pydantic's 422 rather
    than something the handler has to invent a code for."""

    row: int = Field(ge=0, le=2)
    col: int = Field(ge=0, le=2)


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    return authorization.removeprefix("Bearer ")


@app.post("/games/{game_id}/moves")
async def make_move(
    game_id: str,
    body: MoveIn,
    token: Annotated[str, Depends(bearer_token)],
    client: Annotated[object, Depends(get_client)],
    rng: Annotated[random.Random, Depends(get_rng)],
) -> GameView:
    """Validates token, then turn, then square, then persists once.

    In ai mode the model is called inside this same request, so one round trip
    returns a board with both moves in it. Nothing is written until the end:
    both moves are applied to a new board and saved once, so a model failure
    leaves the stored game untouched and the client simply retries its move.

    Existence is checked before taking the lock so that probing unknown ids
    cannot grow the lock dict, and re-checked under it because the game may be
    evicted in between.
    """
    if store.get(game_id) is None:
        raise HTTPException(status_code=404, detail="unknown_game")

    async with store.lock_for(game_id):
        game = store.get(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="unknown_game")

        mark = game.tokens.get(token)
        if mark is None:
            raise HTTPException(status_code=403, detail="not_a_player")
        if status(game.board) != "in_progress":
            raise HTTPException(status_code=409, detail="game_over")
        if current_player(game.board) != mark:
            raise HTTPException(status_code=409, detail="not_your_turn")
        if not is_legal(game.board, body.row, body.col):
            raise HTTPException(status_code=409, detail="square_taken")

        board = apply_move(game.board, body.row, body.col, mark)

        if game.mode == "ai" and status(board) == "in_progress":
            if client is None:
                raise HTTPException(status_code=502, detail="ai_unavailable")
            try:
                ai_move = await choose_move(client, rng, board, opponent(mark), game.difficulty)
            except AIUnavailable:
                raise HTTPException(status_code=502, detail="ai_unavailable") from None
            board = apply_move(board, ai_move.row, ai_move.col, opponent(mark))

        # The single write. Everything above built state; nothing persisted it.
        moved = replace(game, board=board)
        store.save(moved)

    return view(moved)
