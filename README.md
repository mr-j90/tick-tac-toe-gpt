# tick-tac-toe-gpt

A tic-tac-toe JSON API (FastAPI, no frontend): human vs human, or human vs an
OpenAI-backed opponent at three difficulty levels.

## Run it

```sh
uv sync                                  # Python 3.14, pinned in .python-version
uv run uvicorn app.main:app --reload     # http://127.0.0.1:8000, docs at /docs
uv run pytest -m "not live"              # tests; -m live hits the real API
```

`OPENAI_API_KEY` is only needed for `mode: "ai"` — h2h and the whole test suite
run without it. Deployment notes are in `DEPLOY.md`.

## Play

```sh
# 1. create a game — h2h returns two tokens, ai returns one
curl -sX POST localhost:8000/games -H 'content-type: application/json' \
  -d '{"mode":"ai","difficulty":"hard"}'      # or {"mode":"h2h"}

# 2. move, as the player holding that token (X moves first)
curl -sX POST localhost:8000/games/$ID/moves -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"row":1,"col":1}'

# 3. read the board — public, no token; the opponent polls this
curl -s localhost:8000/games/$ID
```

In `h2h` you hand the O token and the game id to your opponent out of band; there
is no lobby. In `ai` mode the model's reply comes back in the same response as
your move. Errors carry a stable code in `detail` (`not_your_turn`,
`square_taken`, `ai_unavailable`, …) so clients branch on a code, not on prose.

## Approach

The board is the only stored state — turn, status and winner are derived from it
on every read, so they can't drift out of sync. Game logic is a pure module with
no FastAPI and no I/O; the API layer is validation plus one write per request.
Storage is an in-process `OrderedDict` capped at 500 games with a per-game
`asyncio.Lock` held across read-validate-write (the AI path awaits a network call
mid-request, so the lock is load-bearing), which is also why deployment is pinned
to a single machine. Difficulty is a blunder rate over one "play well" prompt —
easy 0.7, medium 0.3, hard 0.0 — rather than three prompts to maintain. Model
failures (illegal move, refusal, empty parse) fall through to that same random
picker; transport failures return `502` instead, because silently playing random
moves while the player believes they're facing a model is worse than an error.

## AI tools

Built with Claude Code, driving a four-agent pipeline defined in `CLAUDE.md`:
`pm` → `architect` → `backend` → `qa`, one GitHub issue and one PR per step, with
every merge left to a human. Design decisions were argued out in scratch files
first and locked into `SPEC.md` before any code was written, which is what kept
the agents from re-litigating the same choices on every task. Claude wrote
essentially all of the code and tests; the review, the merges, and the calls on
what to cut were mine.

## What I'd improve

The in-memory store is the big one: it forces the single-machine pin and loses
every in-flight game on deploy. Sub-minute games make that survivable, but Redis
or Postgres is the first thing to add, and scaling out is blocked behind it.
`hard` is raw model play, not a solver — it is beatable, and the tests only
assert the AI plays *legally*, never *well*; a local minimax would fix both and
cost nothing per move. The spend guard caps concurrent AI games, not spend over
time, which needs per-client rate limiting. And polling `GET /games/{id}` is a
placeholder for websockets. The one real surprise was the OpenAI client: built at
import time it breaks keyless CI, and a sync client blocks the event loop for
every other game in flight — it ended up as an async, per-request dependency that
returns `None` when there are no credentials.
