# Tic-tac-toe API — spec

A FastAPI JSON API for tic-tac-toe: human vs human, or human vs an OpenAI-backed opponent at three difficulty levels. No frontend.

Decisions were made in `.scratch/fastapi-tic-tac-toe/` (local, not published); this file is the locked result.

## Toolchain

`uv` for dependencies and virtualenv, `ruff` for lint and format, Python 3.14 pinned via `.python-version`. No type checker.

## Model

A game is:

| Field | Type |
| --- | --- |
| `id` | uuid4 hex |
| `board` | 3x3 nested list of `"X" \| "O" \| None` |
| `mode` | `"h2h" \| "ai"` |
| `difficulty` | `"easy" \| "medium" \| "hard"`, null for `h2h` |
| player tokens | one per human player |

`current_player`, `status` (`in_progress` / `won` / `draw`) and `winner` are **derived from the board on read**, never stored — the board is the single source of truth. X moves first.

**Storage** is an in-process `OrderedDict` capped at 500 games, reached through plain functions (no store interface). LRU eviction past the cap takes the game's lock with it. No timestamps, no sweep, no background task. An evicted game is indistinguishable from one that never existed: `404 unknown_game`. This is correct only on a single machine, so deployment pins the app to one (see Deployment); games are lost on deploy and restart, accepted for sub-minute games.

**Concurrency:** a per-game `asyncio.Lock` held across read-validate-write. Required because the AI path awaits a network call mid-request.

## API

### `POST /games`
Body `{mode, difficulty?}`. `difficulty` is required for `ai`, rejected for `h2h`. Returns the game plus player tokens — two for `h2h`, one for `ai`. The creator passes the O token and game id to their opponent out of band. There is no join endpoint and no lobby.

### `GET /games/{id}`
Public, no token; the unguessable id is the capability. Returns `{id, board, mode, difficulty, current_player, status, winner}`. This is also the polling contract: the waiting player polls until `current_player` is their mark or `status` leaves `in_progress`. No version field, no ETag — the derived turn already answers "has my opponent moved".

### `POST /games/{id}/moves`
`Authorization: Bearer <token>`, body `{row, col}`. Validates token, then turn, then square. In `ai` mode the same request then calls the model and applies its reply, returning a board with both moves in it — one round trip, no background task, so a model failure surfaces in the response the client is already awaiting.

**The handler applies both moves to a new board and persists once, at the end.** On failure nothing was saved, the game is untouched, and the client retries its original move. There is no partial write and therefore no rollback path.

### Errors

`detail` carries a stable snake_case code, so clients and tests branch on a code rather than on prose.

| Status | `detail` |
| --- | --- |
| 404 | `unknown_game` |
| 401 | `missing_token` |
| 403 | `not_a_player` |
| 409 | `not_your_turn`, `square_taken`, `game_over` |
| 502 | `ai_unavailable` |
| 422 | Pydantic default, out-of-range `row`/`col` |

## AI opponent

**Model: `gpt-5.6-luna`, pinned explicitly.** Never the bare `gpt-5.6` — that is an alias for `gpt-5.6-sol`, a different model.

**Call:** `client.responses.parse(model=..., input=..., text_format=Move)` on the Responses API. `Move` is all-required (`row: int`, `col: int`); strict schemas forbid optional fields. Read the result from `resp.output_parsed`.

**Client construction:** a `get_client()` FastAPI dependency, built per request, `AsyncOpenAI(timeout=10.0, max_retries=1)`. It returns **`None` when there are no credentials** rather than raising: the dependency resolves on every move, h2h included, and an h2h game must not require an API key. `None` maps to `502 ai_unavailable`. **Async, not sync**: the move handler awaits the model, and a sync client would block the event loop for every other request in flight, not just the one game its lock protects. **Never at import time** — `OpenAI()` raises without credentials, which would break keyless CI. `get_rng()` sits alongside it, returning `random.Random`.

**Difficulty is a blunder rate** over one "play well" prompt — the probability of substituting a random legal move instead of calling the model:

| Level | Rate |
| --- | --- |
| `easy` | 0.7 |
| `medium` | 0.3 |
| `hard` | 0.0 |

**Failures split two ways:**

- *Model-level* — illegal move, refusal part, `status == "incomplete"`, `output_parsed is None` — falls through to the blunder picker (already there for difficulty). **No retry**: the human is blocked on the request and the 10s timeout bounds it.
- *Transport-level* — `APITimeoutError`, `RateLimitError`, `APIConnectionError`, `APIStatusError` — returns `502 ai_unavailable`. Deliberately not absorbed: if OpenAI is down, falling back would make every move random while the player still believes they face an AI.

**Spend guard.** The app is publicly reachable, so a cap on concurrent `ai` games sits alongside the 500-game store cap: an anonymous caller cannot loop game creation and run the key up. `OPENAI_API_KEY` is set with `fly secrets set` — never in the repo, the image, or `fly.toml`.

**Stated limitation:** `hard` is raw model play. It is not guaranteed optimal and is beatable; guaranteeing optimality needs a local solver, which is out of scope. Tests assert the AI plays *legally*, never that it plays *well*.

## Tests

Two harnesses. Sync unit tests over the pure engine; async in-process HTTP tests (`httpx.AsyncClient` + `ASGITransport`) for everything else — async specifically so a test can fire concurrent requests at one game and prove the lock.

Runner is **anyio's pytest plugin**, already transitive via starlette and httpx2. No new dependency, no `pytest-asyncio`.

The OpenAI double is a **hand-written fake** exposing `.responses.parse`, returning `output_parsed` from a queue of moves the test scripts, injected via `app.dependency_overrides[get_client]`. It mimics the SDK shape on purpose: that is what makes tests execute the real adapter guards. An autouse fixture clears the game and lock dicts between tests.

**Pass bar is a green suite plus this list — no coverage percentage:**

1. All 7 error codes, plus the 422.
2. The 3 SDK failure guards: `incomplete`, refusal, `output_parsed is None`.
3. A full game to a win in each mode, and a draw.
4. Win detection across all 8 lines (unit).
5. An AI illegal move falls through to a legal random move and play continues; a transport error returns 502 with state unchanged.
6. The concurrent-move lock race: two simultaneous POSTs to one game, exactly one applies.
7. LRU eviction at the cap boundary, taking the lock with it.

**Verify before implementing:** that `httpx2` exposes `ASGITransport`. Version numbers were confirmed on 2026-08-29; that API was not.

## CI

One GitHub Actions job: checkout, `astral-sh/setup-uv`, `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest -m "not e2e"`, then `pytest -m e2e` as its own named step. No matrix, no coverage gate.

**The PR job runs with no `OPENAI_API_KEY`** — which also serves as a live check that the client is still built in a dependency rather than at import. An explicit step fails the build if the key is ever present.

**A second job, `live-ai`, runs on merge to `main` only.** It hits the real API with `gpt-5.6-luna` and asserts one move parses. Its purpose is SDK-drift detection: the hand-written fake mimics the response shape, and nothing else would notice if the real shape moved. It asserts the call parses, never that the model plays well. It never runs on pull requests, so the PR gate stays free, deterministic, fork-safe, and keyless.

## Deployment

A `Dockerfile` (uv, `uv sync --frozen --no-dev`, non-root user) and Fly.io hosting.

**Pinned to one machine** — `min_machines_running = 1`, `max_machines_running = 1`, autostop disabled. This is load-bearing, not a cost choice: the store is in-process, so a second machine would give two players two different games. Scaling out requires reopening the storage decision first.

Secrets go through `fly secrets set`. Nothing secret is baked into the image or committed.

## Workflow

Agents **never merge, never approve, never `--admin`**. One ready PR per implementation issue on `issue-<n>-<slug>`; qa runs before the PR opens; red CI returns to the same branch and PR. Human review is a convention here, not branch protection — nothing enforces it.

## Out of scope

Frontend and browser e2e; websockets; accounts and auth beyond a per-game token; branch protection and `CODEOWNERS`; per-client rate limiting; structured logging and request correlation; horizontal scaling (blocked on the storage decision).
