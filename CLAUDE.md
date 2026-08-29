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
