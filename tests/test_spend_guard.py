import httpx2
import pytest

from app import store
from app.main import DEFAULT_MAX_ACTIVE_AI_GAMES, max_active_ai_games

pytestmark = pytest.mark.anyio


async def make_ai(client: httpx2.AsyncClient) -> httpx2.Response:
    return await client.post("/games", json={"mode": "ai", "difficulty": "hard"})


async def make_h2h(client: httpx2.AsyncClient) -> httpx2.Response:
    return await client.post("/games", json={"mode": "h2h"})


def test_default_cap_is_sane() -> None:
    assert max_active_ai_games() == DEFAULT_MAX_ACTIVE_AI_GAMES == 50


def test_cap_is_env_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_ACTIVE_AI_GAMES", "3")
    assert max_active_ai_games() == 3


async def test_an_anonymous_caller_cannot_exceed_the_cap(
    client: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_ACTIVE_AI_GAMES", "3")

    for _ in range(3):
        assert (await make_ai(client)).status_code == 201

    # No credentials anywhere in this loop — the guard is the only thing stopping it.
    for _ in range(10):
        resp = await make_ai(client)
        assert resp.status_code == 429
        assert resp.json()["detail"] == "ai_capacity_reached"


async def test_h2h_is_unaffected_by_the_cap(
    client: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_ACTIVE_AI_GAMES", "1")
    await make_ai(client)
    assert (await make_ai(client)).status_code == 429

    for _ in range(20):
        assert (await make_h2h(client)).status_code == 201, (
            "h2h costs nothing and must not be capped"
        )


async def test_finished_games_free_up_capacity(
    client: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_ACTIVE_AI_GAMES", "1")
    game_id = (await make_ai(client)).json()["id"]
    assert (await make_ai(client)).status_code == 429

    finished = store.get(game_id)
    assert finished is not None
    finished.board = [["X", "X", "X"], ["O", "O", None], [None, None, None]]
    store.save(finished)

    assert store.active_ai_games() == 0
    assert (await make_ai(client)).status_code == 201


async def test_the_counter_only_counts_unfinished_ai_games(client: httpx2.AsyncClient) -> None:
    await make_h2h(client)
    await make_h2h(client)
    assert store.active_ai_games() == 0

    await make_ai(client)
    assert store.active_ai_games() == 1
