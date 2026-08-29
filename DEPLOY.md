# Deploying to Fly.io

The app is a container (see `Dockerfile`) pinned to **one machine**. Read the comment at the top of `fly.toml` before changing anything about scale — the single-machine constraint is a correctness requirement, not a cost setting.

## First deploy

```sh
fly auth login                      # interactive
fly apps create tick-tac-toe-gpt    # or: fly launch --no-deploy
fly secrets set OPENAI_API_KEY      # prompts; never pass the value on the command line
fly deploy --ha=false               # --ha=false prevents the default two-machine pair
fly scale count 1                   # belt and braces: pin the count
```

`fly secrets set` prompts for the value and stores it in Fly's secret store. It is injected as an environment variable at runtime and never enters the image, the repo, `fly.toml`, or a build arg. Passing the value as a command-line argument would put it in your shell history — let the prompt take it.

## Verify

```sh
fly status                          # expect exactly one machine, started
curl https://tick-tac-toe-gpt.fly.dev/health
```

Then play a game end to end:

```sh
curl -X POST https://tick-tac-toe-gpt.fly.dev/games \
  -H 'content-type: application/json' -d '{"mode":"h2h"}'
```

Take the `id` and either token, then post moves to `/games/{id}/moves` with `Authorization: Bearer <token>`.

## Subsequent deploys

```sh
fly deploy --ha=false
```

**Every deploy loses every in-flight game.** The store is in memory, so a restart is a clean slate. That is accepted for sub-minute games; it is the first thing to fix if the app ever needs to survive a rollout.

## What is not configured

- **No autoscaling.** See above.
- **No persistent volume.** Nothing is written to disk.
- **No spend cap beyond `MAX_ACTIVE_AI_GAMES`** (default 50 concurrent AI games). That bounds concurrency, not total spend over time. OpenAI account limits are the real backstop.

## Rolling back

```sh
fly releases                        # list
fly deploy --image <previous-image> # or: fly releases rollback
```
