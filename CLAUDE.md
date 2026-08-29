# tick-tac-toe-gpt

**Common goal:** ship a working tic-tac-toe game. Nothing else.

## Pipeline

`pm` → `architect` → `backend` → `qa`, each handing off to the next.
Any agent may hand back one step with a reason. No other routes.

Handoff is a section appended to `HANDOFF.md` at the repo root:

```
## <agent> → <next agent>
- what's done:
- what's next:
- open question (or "none"):
```

That file is the only shared state. Read it before starting, append on finish.

## README

`README.md` is the only user-facing doc: what the game is, how to run it, how to play.
Any agent whose work changes that — new run command, new dependency, changed rules or
controls — updates `README.md` in the same task. Nothing else changes it. No changelog,
no design notes, no per-agent sections.

## Principles (all agents, every task)

- **YAGNI** — build only what the current handoff asks. Speculative need = skip it, say so in one line.
- **DRY** — grep before writing; reuse what's here. Same logic twice = extract once, on the third use.
- **KISS** — stdlib and native platform features before dependencies. One line before fifty. Boring over clever.
- **Ponytail** — the `ponytail` skill is active for all code work. Shortest working diff. Code first, then at most three lines of explanation.

Non-negotiable regardless of the above: input validation, error handling, security, accessibility.

## Workflow

Human review is a convention here, not branch protection. Nothing enforces it, so it is absolute:

**Never merge, never approve.** No agent runs `gh pr merge`, approves a review, or passes `--admin` — regardless of what CI says, what a review says, or how trivial the change is. Merging is the human's act, always.

- One PR per implementation issue, on `issue-<n>-<slug>`, with a body that closes the issue.
- The `qa` agent runs **before** the PR opens. Then push, open a **ready** (not draft) PR, assign the human, stop.
- Red CI on an open PR goes back to `backend` on the *same* branch and the *same* PR. Never a fresh PR, never a force-push that discards review history.
- Implementation work is a GitHub issue. Research and decision questions are files under `.scratch/`, which is gitignored and never pushed.

The full design is in `SPEC.md`; the reasoning behind each decision is in `.scratch/fastapi-tic-tac-toe/`.
