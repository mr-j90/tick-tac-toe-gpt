# Issue tracker: hybrid (local markdown + GitHub)

Split by kind of work:

- **Planning, research, and decision tickets → local markdown.** Files under `.scratch/<effort>/`. Never pushed to GitHub.
- **Implementation issues → GitHub.** `gh issue create` against `mr-j90/tick-tac-toe-gpt`. These are the only issues that leave the machine.

## Local conventions

- Map: `.scratch/<effort>/map.md`
- Ticket: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with `Type:` (`research`/`prototype`/`grilling`/`task`), `Status:` (`open`/`claimed`/`resolved`), and `Blocked by: NN, NN` lines near the top
- Frontier: open, unblocked, unclaimed tickets; lowest number wins
- Claim: set `Status: claimed` before any work
- Resolve: append the answer under `## Answer`, set `Status: resolved`, append a gist + link to the map's Decisions so far

## GitHub conventions

`gh issue create --title "..." --body "..."` (heredoc for bodies), `gh issue view <n> --comments`, `gh issue edit <n> --add-label`, `gh issue close <n>`.

**Agents never merge or approve a PR.** Every PR waits for human review — enforced by convention, not by branch protection.

## When a skill says "publish to the issue tracker"

Implementation work → GitHub issue. Anything else → a file under `.scratch/<effort>/`.
