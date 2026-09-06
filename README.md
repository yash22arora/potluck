# Potluck

A Telegram group member that figures out what's for dinner and orders it.

It reads the group chat, works out whether tonight is cooking in, ordering in or
going out, and then does something about it over the
[Swiggy MCP](https://mcp.swiggy.com/builders/docs/) — a grocery basket, a food
order, or a table booking. It never spends a rupee without someone tapping
confirm in the group.

> **Status: phase 0.** The skeleton deploys and answers a health check. There is
> no agent yet. See the roadmap below.

## Why it exists

Mostly as a way to learn agent engineering properly — durable state,
human-in-the-loop, memory, evals, and the unglamorous work of making a program
that spends money impossible to make spend it twice. A group chat that argues
about dinner every evening turned out to be a good excuse.

## Design, in four rules

1. Nothing spends money without a human tap. `DRY_RUN` defaults to `true`.
2. A cheap relevance classifier runs before any LLM sees a message, so most of
   the group's chat never leaves the database.
3. Every order is checked against a local ledger *and* Swiggy's own order
   history before it is placed.
4. Every secret comes from the environment, so you can run your own copy.

## Running it

You need Docker and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/yash22arora/potluck.git
cd potluck
make install          # local venv, for tests and linting
make env              # creates .env — fill in what you have
make up               # postgres + api + worker
curl localhost:8000/healthz
```

Then connect a Swiggy account by opening
<http://localhost:8000/auth/swiggy/start> in a browser, and check it worked:

```bash
make probe c="status"
make probe c="tools instamart"
make probe c="search milk"
```

Swiggy tokens last five days and there are no refresh tokens, so that browser
visit comes round again — the bot will ask you when it does.

`/readyz` will tell you what's still missing (database, API keys). Model
provider is configurable — `PLANNER_MODEL` and `GATE_MODEL` take
`provider:model` strings, so Anthropic and OpenAI are both fine, and the two
roles can come from different vendors.

## Layout

```
potluck/    config · llm · logging · main (FastAPI) · worker (scheduler) · db
alembic/    async migrations
docker/     Dockerfile + entrypoint (web | worker | migrate)
docs/       the build plan
```

`CLAUDE.md` carries the working context — architecture, decisions, conventions.

## Roadmap

| # | | |
|---|---|---|
| 0 | Skeleton that deploys | ✅ |
| 1 | Telegram in, echo out | |
| 2 | Swiggy MCP client + OAuth | ✅ |
| 3 | Mock MCP server, dry-run everything | |
| 4 | The day-plan graph, with pause-and-confirm | |
| 5 | Relevance gate + eval set | |
| 6 | Memory: preferences, patterns, "the usual" | |
| 7 | Deduplication, the evening nudge, first real order | |
| 8 | Traces, docs, one-command self-host | |

Details and reasoning in [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md).

## License

MIT.
