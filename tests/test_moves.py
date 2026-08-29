import httpx2
import pytest

from app import store
from app.store import Game

pytestmark = pytest.mark.anyio


async def new_h2h(client: httpx2.AsyncClient) -> tuple[str, dict[str, str]]:
    body = (await client.post("/games", json={"mode": "h2h"})).json()
    return body["id"], body["tokens"]


async def move(
    client: httpx2.AsyncClient, game_id: str, token: str, row: int, col: int
) -> httpx2.Response:
    return await client.post(
        f"/games/{game_id}/moves",
        json={"row": row, "col": col},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_a_legal_move_lands(client: httpx2.AsyncClient) -> None:
    game_id, tokens = await new_h2h(client)
    resp = await move(client, game_id, tokens["X"], 1, 1)
    assert resp.status_code == 200
    body = resp.json()
    assert body["board"][1][1] == "X"
    assert body["current_player"] == "O"


async def test_unknown_game_is_404(client: httpx2.AsyncClient) -> None:
    resp = await move(client, "nope", "any-token", 0, 0)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "unknown_game"


async def test_probing_an_unknown_game_does_not_grow_the_lock_dict(
    client: httpx2.AsyncClient,
) -> None:
    for i in range(20):
        await move(client, f"probe-{i}", "tok", 0, 0)
    assert store._locks == {}, "unknown ids must not allocate locks"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "tok"}, {"Authorization": "Basic tok"}],
    ids=["absent", "no-scheme", "wrong-scheme"],
)
async def test_missing_token_is_401(client: httpx2.AsyncClient, headers: dict) -> None:
    game_id, _ = await new_h2h(client)
    resp = await client.post(f"/games/{game_id}/moves", json={"row": 0, "col": 0}, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing_token"


async def test_a_token_from_another_game_is_403(client: httpx2.AsyncClient) -> None:
    game_id, _ = await new_h2h(client)
    _, other_tokens = await new_h2h(client)
    resp = await move(client, game_id, other_tokens["X"], 0, 0)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "not_a_player"


async def test_moving_out_of_turn_is_409(client: httpx2.AsyncClient) -> None:
    game_id, tokens = await new_h2h(client)
    resp = await move(client, game_id, tokens["O"], 0, 0)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "not_your_turn"


async def test_taking_an_occupied_square_is_409(client: httpx2.AsyncClient) -> None:
    game_id, tokens = await new_h2h(client)
    await move(client, game_id, tokens["X"], 1, 1)
    resp = await move(client, game_id, tokens["O"], 1, 1)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "square_taken"


async def test_moving_in_a_finished_game_is_409(client: httpx2.AsyncClient) -> None:
    _, tokens = await new_h2h(client)
    token_x = next(iter(tokens.values()))
    store.save(
        Game(
            id="done",
            board=[["X", "X", "X"], ["O", "O", None], [None, None, None]],
            mode="h2h",
            difficulty=None,
            tokens={token_x: "X"},
        )
    )
    resp = await move(client, "done", token_x, 2, 2)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "game_over"


@pytest.mark.parametrize(
    ("row", "col"),
    [(-1, 0), (0, -1), (3, 0), (0, 3), (99, 99)],
    ids=["row-neg", "col-neg", "row-high", "col-high", "way-off"],
)
async def test_out_of_range_is_422(client: httpx2.AsyncClient, row: int, col: int) -> None:
    game_id, tokens = await new_h2h(client)
    assert (await move(client, game_id, tokens["X"], row, col)).status_code == 422


@pytest.mark.parametrize(
    ("token_key", "row", "col", "expected"),
    [
        # X has just moved, so it is O's turn: X moving again is out of turn,
        # and O taking X's square is occupied. Order is turn-before-square.
        ("X", 0, 0, "not_your_turn"),
        ("O", 1, 1, "square_taken"),
    ],
    ids=["out-of-turn", "occupied"],
)
async def test_a_rejected_move_leaves_the_board_untouched(
    client: httpx2.AsyncClient, token_key: str, row: int, col: int, expected: str
) -> None:
    game_id, tokens = await new_h2h(client)
    await move(client, game_id, tokens["X"], 1, 1)
    before = (await client.get(f"/games/{game_id}")).json()

    rejected = await move(client, game_id, tokens[token_key], row, col)
    assert rejected.json()["detail"] == expected

    assert (await client.get(f"/games/{game_id}")).json() == before


@pytest.mark.e2e
async def test_full_game_to_a_win(client: httpx2.AsyncClient) -> None:
    game_id, tokens = await new_h2h(client)
    # X takes the top row; O answers along the middle.
    script = [("X", 0, 0), ("O", 1, 0), ("X", 0, 1), ("O", 1, 1), ("X", 0, 2)]

    for mark, row, col in script:
        resp = await move(client, game_id, tokens[mark], row, col)
        assert resp.status_code == 200

    final = resp.json()
    assert final["status"] == "won"
    assert final["winner"] == "X"

    # The game is closed: no further move is accepted.
    assert (await move(client, game_id, tokens["O"], 2, 2)).json()["detail"] == "game_over"


@pytest.mark.e2e
async def test_full_game_to_a_draw(client: httpx2.AsyncClient) -> None:
    game_id, tokens = await new_h2h(client)
    script = [
        ("X", 0, 0),
        ("O", 0, 1),
        ("X", 0, 2),
        ("O", 1, 1),
        ("X", 1, 0),
        ("O", 2, 0),
        ("X", 1, 2),
        ("O", 2, 2),
        ("X", 2, 1),
    ]

    for mark, row, col in script:
        resp = await move(client, game_id, tokens[mark], row, col)
        assert resp.status_code == 200, resp.json()

    final = resp.json()
    assert final["status"] == "draw"
    assert final["winner"] is None
