# Potluck — working context

> This file is the project's memory. Claude Code reads it automatically at the
> start of every session, in any editor. If a decision was made in conversation
> and matters tomorrow, it belongs here, not in a chat log.

## What this is

A Telegram group member that reads the group's conversation, works out whether
tonight is **cook-in**, **order-in** or **eat-out**, and then acts on that over
the [Swiggy MCP](https://mcp.swiggy.com/builders/docs/) — an Instamart basket, a
food order, or a Dineout table. It never spends money without a human tapping
confirm in the group.

It is a learning project first: the goal is production-grade agent engineering
(durable state, human-in-the-loop, memory, evals, idempotent side effects), with
a genuinely useful product as the forcing function.

## Non-negotiables

These are the rules the design exists to serve. Do not quietly relax them.

1. **Nothing spends money without a human tap.** Every irreversible action
   pauses the graph and asks the group. `DRY_RUN` defaults to `true`.
2. **The relevance gate runs before any LLM sees a message.** Group chat is
   private; only food-relevant messages leave the database. Optimise the gate
   for *recall*, not precision.
3. **Read before write.** No `place_food_order` / `checkout` / `book_table`
   without first checking the local ledger *and* Swiggy's own order history.
4. **One config source.** Only `potluck/config.py` reads the environment.
   Everything else takes `get_settings()`. This is what makes self-hosting work.
5. **No secrets, group IDs or addresses in the repo.** Ever.

## Architecture

```
Telegram group ──► relevance gate ──► day-plan graph ──► order ledger ──► Swiggy MCP
                        │                   │  ▲                              (Food /
                    (drops most)            │  └── confirm tap from the group  Instamart /
                                            │                                  Dineout)
                   scheduler (17:30) ───────┘
                                            │
                              Postgres: checkpoints · memory · ledger
```

- **Gate** — a cheap model over a rolling window of the last few messages plus
  the current plan state, so "same as yesterday" and "count me in" survive.
- **Day-plan graph** — LangGraph `StateGraph`. State is one group's plan for one
  day. `thread_id = "{group_id}:{date}"`. Nodes: `interpret → propose → execute
  → record`. It `interrupt()`s at the proposal, so the process can die during
  the pause and resume at the same node when someone taps Confirm.
- **Ledger** — idempotency keyed on `(group, date, meal, surface)`.
- **Memory** — three deliberately different stores: structured facts (brand
  preferences, diets, cutoff time) with confidence + last-confirmed date; an
  episodic log of what actually happened each night; pgvector *only* for fuzzy
  recall ("the usual"). Patterns are derived in code from Swiggy order history,
  not by asking a model to notice them.

## Phases

Full plan with rationale: `docs/BUILD_PLAN.md`.

| # | Phase | State |
|---|-------|-------|
| 0 | Skeleton that deploys | **done** |
| 1 | Telegram in, echo out | next |
| 2 | Swiggy MCP client + OAuth, no agent | |
| 3 | Mock MCP server + `DRY_RUN` | |
| 4 | Day-plan graph with `interrupt()` | the key phase |
| 5 | Relevance gate + eval set | |
| 6 | Memory | |
| 7 | Dedup, nudge, first real order | |
| 8 | Observability + self-host packaging | |

Rules of order: 3 strictly before 4. 5 and 6 may swap. 7 cannot move — it must
exist before the first real order.

## Layout

```
potluck/
  config.py      every env var, single source of truth
  llm.py         get_chat_model("planner"|"gate") — provider-agnostic
  logging.py     structlog: console locally, JSON in deploy
  main.py        FastAPI: / · /healthz · /readyz
  worker.py      APScheduler process (same image, different command)
  db/            base · models · session
alembic/         async migrations, URL comes from config not alembic.ini
docker/          Dockerfile + entrypoint.sh (web | worker | migrate)
tests/
docs/
```

Planned, not yet written: `telegram/`, `gate/`, `graph/`, `swiggy/`, `memory/`.

## Commands

```bash
make install      # uv sync --all-groups
make env          # .env from .env.example
make up           # docker compose up --build -d   → :8000
make logs
make test
make lint / fmt
make revision m="add messages"   # autogenerate a migration
make migrate                     # apply against the running db
```

## Decisions already made (don't relitigate without reason)

- **LangGraph, not bare LangChain** — the Postgres checkpointer and
  `interrupt()` are the entire reason. Nothing else here needs LangChain.
- **Provider-agnostic models** — `init_chat_model` with `"provider:model"`
  strings. Planner and gate are separate roles so phase 5 can put a cheap model
  on the hot path without touching the planner.
- **One Postgres for everything** — checkpoints, memory, ledger, embeddings.
  pgvector is enabled in migration `0001`. No separate vector database.
- **One image, three commands** — `docker/entrypoint.sh` switches on
  `web|worker|migrate`. Avoids a second Dockerfile drifting out of sync.
- **`/healthz` never touches the database** — liveness must not fail on a db
  blip or the platform will kill a healthy process. `/readyz` does the real
  checks.
- **Railway** as the deploy target (`railway.json`), chosen for managed
  Postgres and Dockerfile builds.
- **Distribution model: one container per household.** Simpler than
  multi-tenant — no shared token vault, no cross-group leakage. Costs nothing
  as long as rules 4 and 5 above hold.

## Open questions

- **Swiggy production access is granted per developer, after a demo video.** If
  every self-hosting user needs their own OAuth client, "clone and run" has a
  gate we don't control. Ask `builders@swiggy.in` during phase 2 whether one
  registered client can serve a distributed self-hosted app. The answer
  reshapes phase 8.
- Swiggy MCP server URLs are unset in `.env.example` — fill them from the
  builders console.

## Conventions

- Python 3.12, `uv` for everything. `ruff` for lint and format, line length 100.
- Async all the way down: async SQLAlchemy, async httpx, no blocking calls in a
  request or graph node.
- Every LLM output is a Pydantic model. Never parse free text.
- Docstrings explain *why*, not what. The code says what.
- Migrations are always reviewed before commit — `--autogenerate` guesses, and
  it guesses wrong about types and server defaults.
