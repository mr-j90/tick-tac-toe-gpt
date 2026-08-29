import pytest

from app.engine import (
    LINES,
    Board,
    apply_move,
    current_player,
    empty_board,
    is_full,
    is_legal,
    status,
    winner,
)


def board_from(rows: list[str]) -> Board:
    """'X.O' -> ['X', None, 'O']. Keeps test boards readable."""
    return [[None if ch == "." else ch for ch in row] for row in rows]


def test_empty_board_is_blank() -> None:
    assert empty_board() == [[None] * 3 for _ in range(3)]
    assert status(empty_board()) == "in_progress"
    assert winner(empty_board()) is None


@pytest.mark.parametrize("line", LINES, ids=[str(line[0]) + "-" + str(line[2]) for line in LINES])
def test_every_winning_line_is_detected(line: list[tuple[int, int]]) -> None:
    board = empty_board()
    for r, c in line:
        board[r][c] = "X"
    assert winner(board) == "X"
    assert status(board) == "won"


def test_no_winner_on_a_scattered_board() -> None:
    board = board_from(["XO.", "OX.", "..O"])
    assert winner(board) is None
    assert status(board) == "in_progress"


def test_draw_is_a_full_board_with_no_winner() -> None:
    board = board_from(["XOX", "XOO", "OXX"])
    assert is_full(board)
    assert winner(board) is None
    assert status(board) == "draw"


def test_full_board_with_a_winner_is_won_not_drawn() -> None:
    board = board_from(["XXX", "OOX", "OXO"])
    assert is_full(board)
    assert status(board) == "won"


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (["...", "...", "..."], "X"),
        (["X..", "...", "..."], "O"),
        (["XO.", "...", "..."], "X"),
        (["XOX", "O..", "..."], "X"),
        (["XOX", "OX.", "..."], "O"),
    ],
    ids=["empty", "one-x", "one-each", "four-even", "five-odd"],
)
def test_turn_derivation(rows: list[str], expected: str) -> None:
    assert current_player(board_from(rows)) == expected


@pytest.mark.parametrize(
    ("row", "col", "legal"),
    [
        (0, 1, True),
        (0, 0, False),
        (2, 2, False),
        (-1, 0, False),
        (0, -1, False),
        (3, 0, False),
        (0, 3, False),
    ],
    ids=["empty", "occupied-x", "occupied-o", "row-neg", "col-neg", "row-high", "col-high"],
)
def test_move_legality(row: int, col: int, legal: bool) -> None:
    assert is_legal(board_from(["X..", "...", "..O"]), row, col) is legal


def test_apply_move_returns_a_new_board_and_never_mutates() -> None:
    before = empty_board()
    after = apply_move(before, 1, 1, "X")
    assert after[1][1] == "X"
    assert before == empty_board(), "apply_move must not mutate its input"
    assert after is not before
