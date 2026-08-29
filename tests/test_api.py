import httpx2
import pytest

from app import store
from app.engine import empty_board
from app.store import Game

pytestmark = pytest.mark.anyio


async def create(client: httpx2.AsyncClient, **body: object) -> httpx2.Response:
    return await client.post("/games", json=body)


async def test_h2h_returns_two_tokens(client: httpx2.AsyncClient) -> None:
    resp = await create(client, mode="h2h")
    assert resp.status_code == 201
    body = resp.json()
    assert sorted(body["tokens"]) == ["O", "X"]
    assert body["tokens"]["X"] != body["tokens"]["O"]
    assert body["mode"] == "h2h"
    assert body["difficulty"] is None


async def test_ai_returns_one_token(client: httpx2.AsyncClient) -> None:
    resp = await create(client, mode="ai", difficulty="hard")
    assert resp.status_code == 201
    body = resp.json()
    assert list(body["tokens"]) == ["X"]
    assert body["difficulty"] == "hard"


async def test_new_game_is_empty_and_x_to_move(client: httpx2.AsyncClient) -> None:
    body = (await create(client, mode="h2h")).json()
    assert body["board"] == [[None] * 3 for _ in range(3)]
    assert body["current_player"] == "X"
    assert body["status"] == "in_progress"
    assert body["winner"] is None


async def test_tokens_are_unguessable(client: httpx2.AsyncClient) -> None:
    a = (await create(client, mode="h2h")).json()["tokens"]["X"]
    b = (await create(client, mode="h2h")).json()["tokens"]["X"]
    assert a != b
    assert len(a) >= 32


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "ai"},
        {"mode": "h2h", "difficulty": "easy"},
        {"mode": "nonsense"},
        {"mode": "ai", "difficulty": "impossible"},
        {},
    ],
    ids=["ai-without-difficulty", "h2h-with-difficulty", "bad-mode", "bad-difficulty", "empty"],
)
async def test_invalid_create_bodies_are_rejected(client: httpx2.AsyncClient, body: dict) -> None:
    assert (await client.post("/games", json=body)).status_code == 422


async def test_read_is_public(client: httpx2.AsyncClient) -> None:
    game_id = (await create(client, mode="h2h")).json()["id"]
    resp = await client.get(f"/games/{game_id}")
    assert resp.status_code == 200
    assert "authorization" not in {k.lower() for k in resp.request.headers}
    assert "tokens" not in resp.json(), "reading must not leak either player's token"


async def test_unknown_game_is_404(client: httpx2.AsyncClient) -> None:
    resp = await client.get("/games/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "unknown_game"


async def test_derived_fields_on_a_mid_game_board(client: httpx2.AsyncClient) -> None:
    board = [["X", "X", None], ["O", "O", None], [None, None, None]]
    store.save(Game(id="mid", board=board, mode="h2h", difficulty=None, tokens={}))

    body = (await client.get("/games/mid")).json()

    assert body["current_player"] == "X"
    assert body["status"] == "in_progress"
    assert body["winner"] is None


async def test_derived_fields_on_a_won_board(client: httpx2.AsyncClient) -> None:
    board = [["O", "O", "O"], ["X", "X", None], [None, None, None]]
    store.save(Game(id="won", board=board, mode="h2h", difficulty=None, tokens={}))

    body = (await client.get("/games/won")).json()

    assert body["status"] == "won"
    assert body["winner"] == "O"


async def test_evicted_game_reads_the_same_as_one_that_never_existed(
    client: httpx2.AsyncClient,
) -> None:
    store.save(Game(id="doomed", board=empty_board(), mode="h2h", difficulty=None, tokens={}))
    for i in range(store.MAX_GAMES):
        store.save(Game(id=f"g{i}", board=empty_board(), mode="h2h", difficulty=None, tokens={}))

    evicted = await client.get("/games/doomed")
    never = await client.get("/games/never-existed")

    assert evicted.status_code == never.status_code == 404
    assert evicted.json() == never.json()
