"""Pure game logic. No FastAPI, no I/O, no state.

Turn and status are derived from the board on every call rather than stored,
so they cannot drift from it — the board is the single source of truth.
"""

from typing import Literal

Mark = Literal["X", "O"]
Board = list[list[str | None]]
Status = Literal["in_progress", "won", "draw"]

SIZE = 3

# The 8 winning lines, derived rather than written out as 24 coordinate pairs.
LINES: list[list[tuple[int, int]]] = (
    [[(r, c) for c in range(SIZE)] for r in range(SIZE)]
    + [[(r, c) for r in range(SIZE)] for c in range(SIZE)]
    + [
        [(i, i) for i in range(SIZE)],
        [(i, SIZE - 1 - i) for i in range(SIZE)],
    ]
)


def empty_board() -> Board:
    return [[None] * SIZE for _ in range(SIZE)]


def current_player(board: Board) -> Mark:
    """X moves first, so X is up whenever both marks are equally represented."""
    counts = [cell for row in board for cell in row]
    return "X" if counts.count("X") == counts.count("O") else "O"


def winner(board: Board) -> Mark | None:
    for line in LINES:
        a, b, c = (board[r][col] for r, col in line)
        if a is not None and a == b == c:
            return a  # type: ignore[return-value]
    return None


def is_full(board: Board) -> bool:
    return all(cell is not None for row in board for cell in row)


def status(board: Board) -> Status:
    if winner(board) is not None:
        return "won"
    return "draw" if is_full(board) else "in_progress"


def opponent(mark: Mark) -> Mark:
    return "O" if mark == "X" else "X"


def is_legal(board: Board, row: int, col: int) -> bool:
    """In range and empty. Whose turn it is belongs to the caller, not here."""
    if not (0 <= row < SIZE and 0 <= col < SIZE):
        return False
    return board[row][col] is None


def apply_move(board: Board, row: int, col: int, mark: Mark) -> Board:
    """Return a NEW board with the move applied.

    Never mutates: the move handler builds the next state and persists once, so
    a failure part-way through leaves the stored game untouched.
    """
    return [
        [mark if (r, c) == (row, col) else cell for c, cell in enumerate(line)]
        for r, line in enumerate(board)
    ]
