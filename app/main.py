import secrets
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator

from app import store
from app.engine import Board, Mark, Status, current_player, empty_board, status, winner
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
