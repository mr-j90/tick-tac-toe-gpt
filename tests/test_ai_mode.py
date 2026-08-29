import asyncio
import random
from collections.abc import Callable, Iterator

import httpx2
import openai
import pytest

from app import store
from app.ai import Move, get_client, get_rng
from app.main import app
from tests.conftest import FakeClient, response

pytestmark = pytest.mark.anyio


class SlowResponses:
    """Yields control mid-call, so two in-flight requests can actually interleave
    if the lock is not holding them apart."""

    def __init__(self, script: list[object]) -> None:
        self.script = script
        self.calls: list[dict] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        await asyncio.sleep(0.01)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def slow_client(*script: object) -> FakeClient:
    c = FakeClient()
    c.responses = SlowResponses(list(script))
    return c


@pytest.fixture
def use_ai() -> Iterator[Callable[..., None]]:
    def _use(client_obj: object, rng: random.Random | None = None) -> None:
        app.dependency_overrides[get_client] = lambda: client_obj
        app.dependency_overrides[get_rng] = lambda: rng or random.Random(0)

    yield _use
    app.dependency_overrides.clear()


async def new_ai_game(client: httpx2.AsyncClient, difficulty: str = "hard") -> tuple[str, str]:
    body = (await client.post("/games", json={"mode": "ai", "difficulty": difficulty})).json()
    return body["id"], body["tokens"]["X"]


async def move(
    client: httpx2.AsyncClient, game_id: str, token: str, row: int, col: int
) -> httpx2.Response:
    return await client.post(
        f"/games/{game_id}/moves",
        json={"row": row, "col": col},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_one_round_trip_returns_both_moves(
    client: httpx2.AsyncClient, use_ai: Callable[..., None]
) -> None:
    use_ai(FakeClient(response(output_parsed=Move(row=1, col=1))))
    game_id, token = await new_ai_game(client)

    body = (await move(client, game_id, token, 0, 0)).json()

    assert body["board"][0][0] == "X", "the human's move"
    assert body["board"][1][1] == "O", "the model's reply, in the same response"
    assert body["current_player"] == "X", "back to the human"


async def test_transport_failure_is_502_and_leaves_the_game_untouched(
    client: httpx2.AsyncClient, use_ai: Callable[..., None]
) -> None:
    use_ai(FakeClient(openai.APITimeoutError(request=None)))
    game_id, token = await new_ai_game(client)
    before = (await client.get(f"/games/{game_id}")).json()

    resp = await move(client, game_id, token, 0, 0)

    assert resp.status_code == 502
    assert resp.json()["detail"] == "ai_unavailable"
    assert (await client.get(f"/games/{game_id}")).json() == before, (
        "the human's move must not survive a failed AI turn — nothing is persisted "
        "until both moves are applied"
    )


async def test_no_credentials_is_502(
    client: httpx2.AsyncClient, use_ai: Callable[..., None]
) -> None:
    use_ai(None)
    game_id, token = await new_ai_game(client)

    resp = await move(client, game_id, token, 0, 0)

    assert resp.status_code == 502
    assert resp.json()["detail"] == "ai_unavailable"


async def test_h2h_never_touches_the_model(client: httpx2.AsyncClient, use_ai: Callable) -> None:
    use_ai(FakeClient())  # empty script: any model call raises
    body = (await client.post("/games", json={"mode": "h2h"})).json()

    resp = await move(client, body["id"], body["tokens"]["X"], 0, 0)

    assert resp.status_code == 200


async def test_the_model_does_not_move_after_the_human_wins(
    client: httpx2.AsyncClient, use_ai: Callable[..., None]
) -> None:
    use_ai(FakeClient())  # empty script: a model call would raise
    game_id, token = await new_ai_game(client)
    store.save(
        store.Game(
            id=game_id,
            board=[["X", "X", None], ["O", "O", None], [None, None, None]],
            mode="ai",
            difficulty="hard",
            tokens={token: "X"},
        )
    )

    body = (await move(client, game_id, token, 0, 2)).json()

    assert body["status"] == "won"
    assert body["winner"] == "X"


async def test_concurrent_moves_on_one_game_serialise(
    client: httpx2.AsyncClient, use_ai: Callable[..., None]
) -> None:
    """The reason the per-game lock exists: the model call is an await between
    read and write, so without it both requests would read the same board."""
    ai = slow_client(
        response(output_parsed=Move(row=1, col=1)),
        response(output_parsed=Move(row=2, col=2)),
    )
    use_ai(ai)
    game_id, token = await new_ai_game(client)

    first, second = await asyncio.gather(
        move(client, game_id, token, 0, 0),
        move(client, game_id, token, 0, 0),
    )

    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409], f"exactly one move should apply, got {codes}"
    rejected = first if first.status_code == 409 else second
    assert rejected.json()["detail"] == "square_taken"
    assert len(ai.responses.calls) == 1, "the losing request must not reach the model"


@pytest.mark.e2e
async def test_full_ai_game_plays_to_completion(
    client: httpx2.AsyncClient, use_ai: Callable[..., None]
) -> None:
    """The model answers with an occupied square every time, so every AI turn
    takes the illegal-move fallback. The game must still finish."""
    ai = FakeClient(*[response(output_parsed=Move(row=0, col=0)) for _ in range(5)])
    use_ai(ai, random.Random(7))
    game_id, token = await new_ai_game(client)

    seen = set()
    for row, col in [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]:
        resp = await move(client, game_id, token, row, col)
        if resp.status_code == 409:
            continue  # the AI took that square
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        seen.add(body["status"])
        if body["status"] != "in_progress":
            break

    assert body["status"] in {"won", "draw"}
    flat = [cell for r in body["board"] for cell in r]
    assert flat.count("X") >= 1 and flat.count("O") >= 1
