import asyncio

import pytest

from app import store
from app.engine import empty_board
from app.store import MAX_GAMES, Game


def make(game_id: str) -> Game:
    return Game(
        id=game_id,
        board=empty_board(),
        mode="h2h",
        difficulty=None,
        tokens={f"tok-{game_id}-x": "X", f"tok-{game_id}-o": "O"},
    )


def test_save_and_get_round_trip() -> None:
    store.save(make("g1"))
    got = store.get("g1")
    assert got is not None and got.id == "g1"


def test_unknown_id_is_none() -> None:
    assert store.get("never-existed") is None


def test_eviction_fires_at_the_cap_boundary() -> None:
    for i in range(MAX_GAMES):
        store.save(make(f"g{i}"))
    assert store.count() == MAX_GAMES
    assert store.get("g0") is not None, "nothing should be evicted at exactly the cap"

    # g0 was just read, so the oldest untouched game is g1.
    store.save(make("one-more"))

    assert store.count() == MAX_GAMES
    assert store.get("g1") is None, "the least recently used game should be gone"
    assert store.get("g0") is not None, "reading g0 should have spared it"
    assert store.get("one-more") is not None


def test_evicted_game_is_indistinguishable_from_one_that_never_existed() -> None:
    for i in range(MAX_GAMES + 1):
        store.save(make(f"g{i}"))
    assert store.get("g0") is store.get("never-existed") is None


def test_eviction_removes_the_lock_too() -> None:
    store.save(make("doomed"))
    store.lock_for("doomed")
    assert "doomed" in store._locks

    for i in range(MAX_GAMES):
        store.save(make(f"g{i}"))

    assert store.get("doomed") is None
    assert "doomed" not in store._locks, "the leak would just relocate to the lock dict"


def test_lock_for_returns_the_same_lock_per_game() -> None:
    assert store.lock_for("g1") is store.lock_for("g1")
    assert store.lock_for("g1") is not store.lock_for("g2")


@pytest.mark.anyio
async def test_the_lock_actually_serialises() -> None:
    """The reason the lock exists: an await between read and write must not
    let a second caller interleave."""
    order: list[str] = []

    async def worker(name: str) -> None:
        async with store.lock_for("g1"):
            order.append(f"{name}-in")
            await asyncio.sleep(0)
            order.append(f"{name}-out")

    await asyncio.gather(worker("a"), worker("b"))

    assert order in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    ), f"interleaved: {order}"


def test_autouse_fixture_isolates_tests_part_one() -> None:
    store.save(make("leaky"))
    assert store.count() == 1


def test_autouse_fixture_isolates_tests_part_two() -> None:
    assert store.count() == 0, "state leaked from the previous test"
