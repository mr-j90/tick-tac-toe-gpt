"""In-process game store.

A module-level dict reached through plain functions — deliberately not a class
or an interface, since there is exactly one implementation. The swap point if a
second worker ever appears is these function bodies, not an abstraction layered
over them now.

ponytail: single-process only. Correct because deployment pins the app to one
machine; two machines would give two players two different games. Scaling out
means replacing these bodies with a shared store first.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from app.engine import Board, Mark, status

MAX_GAMES = 500

Mode = Literal["h2h", "ai"]
Difficulty = Literal["easy", "medium", "hard"]


@dataclass
class Game:
    id: str
    board: Board
    mode: Mode
    difficulty: Difficulty | None
    tokens: dict[str, Mark]
    """Token -> mark. Stored in the direction auth reads it; the create response
    inverts it to hand each player their own token."""


_games: OrderedDict[str, Game] = OrderedDict()
_locks: dict[str, asyncio.Lock] = {}


def get(game_id: str) -> Game | None:
    """Fetch a game, marking it recently used. None for unknown *and* evicted
    ids alike — a caller cannot distinguish the two, which is correct: both mean
    the id is no longer playable."""
    game = _games.get(game_id)
    if game is not None:
        _games.move_to_end(game_id)
    return game


def save(game: Game) -> None:
    _games[game.id] = game
    _games.move_to_end(game.id)
    _evict()


def lock_for(game_id: str) -> asyncio.Lock:
    """The lock a move handler holds across read-validate-write."""
    return _locks.setdefault(game_id, asyncio.Lock())


def count() -> int:
    return len(_games)


def active_ai_games() -> int:
    """Games that can still burn tokens: ai mode, not yet finished.

    ponytail: O(n) over at most MAX_GAMES on each ai-game creation. A counter
    kept in sync would be faster and would be one more thing to desync from the
    board, which is the source of truth.
    """
    return sum(1 for g in _games.values() if g.mode == "ai" and status(g.board) == "in_progress")


def clear() -> None:
    """Reset. Used by the autouse test fixture."""
    _games.clear()
    _locks.clear()


def _evict() -> None:
    while len(_games) > MAX_GAMES:
        evicted_id, _ = _games.popitem(last=False)
        # The lock goes with the game, or the leak simply relocates here.
        # A request holding this lock keeps its own reference and finishes
        # safely; the game is gone, so its next lookup is a miss.
        _locks.pop(evicted_id, None)
