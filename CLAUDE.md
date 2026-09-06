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
| 2 | Swiggy MCP client + OAuth, no agent | **done** |
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
  crypto.py      Fernet encryption for tokens at rest
  api/           swiggy_auth.py — /auth/swiggy/{start,callback,status}
  swiggy/        servers · oauth · tokens · client
  scripts/       probe.py — talk to Swiggy with no agent involved
  db/            base · models · session
alembic/         async migrations, URL comes from config not alembic.ini
docker/          Dockerfile + entrypoint.sh (web | worker | migrate)
tests/
docs/
```

Planned, not yet written: `telegram/`, `gate/`, `graph/`, `memory/`, `swiggy/mock.py`.

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

make env                         # safe to re-run: backfills new keys, keeps yours
make auth                        # prints the URL that links a Swiggy account
make probe c="status"            # token state, no network
make probe c="tools instamart"   # list a surface's tools
make probe c="search milk"       # call search_products
```

## Swiggy MCP: the facts that shape the design

Docs: [authenticate](https://mcp.swiggy.com/builders/docs/start/authenticate/) ·
[build an agent](https://mcp.swiggy.com/builders/docs/start/developer/build-an-agent/)

Surfaces (fixed URLs, streamable HTTP, `Authorization: Bearer <token>`):

| Surface | URL | Tools |
|---|---|---|
| Food | `https://mcp.swiggy.com/food` | 18 |
| Instamart | `https://mcp.swiggy.com/im` | 19 |
| Dineout | `https://mcp.swiggy.com/dineout` | 12 |

**It is `/im`, not `/instamart`.**

Four properties of Swiggy's OAuth that are not negotiable and that the code is
built around:

1. **No client_id in a dashboard.** Dynamic client registration, RFC 7591:
   `POST /auth/register` at runtime returns one. It is bound to an exact
   redirect URI, so local and deployed each register separately. Stored in
   `swiggy_oauth_clients`.
2. **No refresh tokens in v1.** The access token lasts 5 days (`expires_in`
   432000) and then it is gone. Nothing can renew it in the background — a
   human has to open a browser. `SwiggyToken.needs_reauth` is how that
   propagates; phase 7 must surface it in the group chat, not fail silently.
3. **401 and 419 mean re-authorize, never retry.** 401 = expired or invalid,
   419 = session revoked, 403 = insufficient scope. `SwiggyClient` walks the
   exception chain for these and converts them into `NeedsAuthorization`.
4. **Redirect allowlist is exact-match, no wildcards.** `http://localhost` is
   the one non-HTTPS exception, which is what makes local development work.

Other details: PKCE is S256 over a 32-byte verifier; scopes are `mcp:tools`,
`mcp:resources`, `mcp:prompts`; the authorization code is single-use and lives
120 seconds, so it is exchanged inside the callback handler; access to the three
surfaces is granted per *user*, not per application.

### MCP Python SDK 2.x

We are on `mcp>=2.1`. Four differences from the 1.x examples you will find in
most blog posts and in Swiggy's own docs — each one is an import-time or
first-call crash:

| 1.x | 2.x |
|---|---|
| `streamablehttp_client` | `streamable_http_client` |
| `headers=` parameter | pass a configured `http_client` |
| yields 3 streams | yields 2 |
| `httpx` | `httpx2` (a separate package) |

So the shape is:

```python
async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {t}"}) as http:
    async with streamable_http_client(url, http_client=http) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
```

`tests/test_mcp_sdk_contract.py` pins all of this, so the next rename fails in
CI rather than at dinner time.

One consequence worth knowing: for tool calls the SDK turns a non-2xx response
into a JSON-RPC error and **the HTTP status is lost**. That is why
`SwiggyClient` falls back to `_ask_server_about_token` — a plain GET on the
surface URL that reads only the status line — instead of trying to infer 401
from an error message.

Tokens are encrypted at rest with Fernet, keyed off `SECRET_KEY`. Changing that
variable invalidates every stored token — the cure is re-authorizing, and
`crypto.decrypt` says so in its error.

## Deferred requirements

Agreed but not built. Do not lose these; do not build them early either.

### Address selection (raised Sep 6, phase 2)

Instamart's `search_products` — and every cart and checkout call after it —
requires an `addressId`. The account has ~10 saved addresses spanning home,
two offices and several friends' places, so there is no safe default.

Swiggy's own `get_addresses` response says as much: it returns
`resolution.needsUserClarification: true` alongside a `candidateAddressIds`
list. The API is declining to guess, and neither should we.

The requirement:

1. **Resolve the delivery address once, at boot**, and cache it. Every
   subsequent Swiggy call reuses it rather than re-resolving.
2. **The user can change it at any time by talking to the bot** — "we're at
   Saksham's tonight", "order to the office" — conversationally, not by
   editing config or restarting anything.

Design notes for whoever builds it (phase 4 or a small phase 3.5):

- This is a **third human-in-the-loop moment**, alongside order confirmation
  and the re-authorization prompt. Same `interrupt()` primitive. On first boot
  with no cached address, the bot asks the group which one and waits.
- Cache it as a **structured fact** in the phase-6 facts store (`address_id`
  plus its tag, with `last_confirmed`), not in a config file — it is exactly
  the kind of thing that store exists for, and it should decay: if the last
  confirmation is weeks old, re-confirm rather than assume.
- Match on the **tag** ("Home", "Work", "Saksham's Home"), because that is what
  a human will say. Keep the id internal; never make anyone type it.
- Address ids and address lines are personal data. They belong in the database,
  never in logs, never in a repo file, and never in an LLM prompt beyond the
  tag and the id.
- A wrong address is a silent, expensive failure — the food arrives somewhere
  real, just not where anyone is. Treat a change of address as needing
  confirmation, the same as spending money.

Until then, `SWIGGY_DEV_ADDRESS_ID` in `.env` is a **development shim only**,
used by the probe script. Nothing in the agent may read it.

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
- **Swiggy tokens encrypted at rest**, not stored plaintext. A token is five
  days of spending authority.
- **`account_key` on the token**, not a hardcoded single user. It is `"default"`
  today and becomes the Telegram user id of whoever's Swiggy account pays once
  the group has members.
- **Token exchange sends form-encoded first, JSON on 4xx.** OAuth specifies
  form; Swiggy's docs show JSON. Trying both beats guessing.
- **`tools/bootstrap_env.py` backfills .env** rather than only creating it, so
  keys added to `.env.example` later reach an existing `.env`. `make env` is
  safe to re-run and never overwrites a value you set.
- **Distribution model: one container per household.** Simpler than
  multi-tenant — no shared token vault, no cross-group leakage. Costs nothing
  as long as rules 4 and 5 above hold.

## Open questions

- **Swiggy production access is granted per developer, after a demo video.** If
  every self-hosting user needs their own OAuth client, "clone and run" has a
  gate we don't control. Ask `builders@swiggy.in` during phase 2 whether one
  registered client can serve a distributed self-hosted app. The answer
  reshapes phase 8.
- ~~Swiggy MCP server URLs~~ — resolved, they are fixed and in the table above.
- Production access is still gated on a demo video; localhost is whitelisted for
  development, which is what phase 2 through 7 run against.

## Conventions

- Python 3.12, `uv` for everything. `ruff` for lint and format, line length 100.
- Async all the way down: async SQLAlchemy, async httpx, no blocking calls in a
  request or graph node.
- Every LLM output is a Pydantic model. Never parse free text.
- Docstrings explain *why*, not what. The code says what.
- Migrations are always reviewed before commit — `--autogenerate` guesses, and
  it guesses wrong about types and server defaults.
