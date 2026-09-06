# Build plan

Eight phases. Each ends in something runnable you can show someone. Nothing
spends real money before phase 7, and even then only behind `DRY_RUN=false`.

Rules of order: **3 strictly before 4** (the mock is what makes the interesting
phases fast and free). **5 and 6 may swap.** **7 cannot move** — deduplication
has to exist before the first real order.

---

## 0 — A skeleton that already deploys ✅

Do the boring cloud work while there is nothing to break.

- `uv` project, Python 3.12, ruff, pytest
- `potluck/config.py` — the single source of environment truth
- `potluck/llm.py` — `get_chat_model("planner"|"gate")`, provider-agnostic
- FastAPI with `/healthz` (liveness, no dependencies) and `/readyz` (database +
  model config)
- Async SQLAlchemy, Alembic wired to read the URL from config, pgvector enabled
  in migration `0001`
- Multi-stage Dockerfile, `entrypoint.sh` switching `web|worker|migrate`,
  compose with a pgvector Postgres
- GitHub Actions: lint, migrations, tests, image build
- `railway.json`

**Done when** a public URL returns `{"status":"ok"}` and a push to main
redeploys it.

**You learn** that deployment is never the thing blocking you later.

---

## 1 — Telegram in, echo out

Bot registered, `setWebhook` with a secret token, updates landing in a
`messages` table with group, sender and timestamp. Reply to `/ping`.

The interesting part is that Telegram retries on a slow response, so the handler
must be idempotent — store the update id and ignore repeats.

**Done when** it echoes in a real group and duplicate deliveries do not create
duplicate rows.

**You learn** webhook mechanics and at-least-once delivery.

---

## 2 — Talk to Swiggy, with no agent anywhere

OAuth 2.1 with PKCE: `/auth/swiggy/start` redirects, `/auth/swiggy/callback`
stores tokens. Then a plain script that connects over streamable HTTP, calls
`get_addresses` and `search_products`, and prints what comes back.

No LLM involved. The point is to see the protocol clearly before anything is
reasoning about it.

**Done when** `uv run python -m potluck.scripts.probe milk` prints real
Instamart products.

**You learn** MCP from the client side, and a real OAuth handshake.

---

## 3 — A fake Swiggy you control

Your own MCP server mirroring the real tool schemas, with switches for
out-of-stock, `PENDING_PAYMENT`, a taken Dineout slot, and a timeout.
`DRY_RUN=true` routes every Swiggy call here.

Unglamorous and load-bearing: you will iterate on prompts and thresholds dozens
of times, and you want that free, offline and deterministic.

**Done when** the whole test suite runs with no network, and you can make any
failure happen on demand.

**You learn** the protocol properly — writing a server teaches it far better
than calling one does.

---

## 4 — The day-plan graph

The key phase.

A LangGraph `StateGraph` whose state is one group's plan for one day: mode
(undecided / cooking / ordering / going out), the proposed cart, who has weighed
in. Nodes `interpret → propose → execute → record`. `AsyncPostgresSaver` as the
checkpointer, `thread_id = "{group_id}:{date}"`, and `interrupt()` at the
proposal so a Telegram button resumes it.

**Done when** "let's order biryani" produces a proposal card, you restart the
container mid-pause, and tapping Confirm still completes the order against the
mock.

**You learn** durable execution and human-in-the-loop — the thing people mean
when they say they have built an agent.

---

## 5 — The relevance gate

A cheap classifier over a rolling window of the last few messages plus the
current plan state, so "same as yesterday" and "count me in" survive while the
rest never leaves the database.

Build the labelled set *first*, then the classifier. Optimise for recall: a
dropped relevant message is unrecoverable, a kept irrelevant one is just noise
the planner ignores.

**Done when** recall is above 0.95 on the eval set, most messages are dropped,
and the score prints in CI.

**You learn** model routing by cost, and eval discipline — a number you can
point at instead of a vibe.

---

## 6 — Memory that earns its name

Three stores, deliberately different:

- **Facts** — rows with a confidence and a last-confirmed date, so March's milk
  brand decays if the last three orders disagree.
- **Episodes** — what actually happened each night.
- **Recall** — pgvector, and *only* for fuzzy lookups: "the usual", "that place
  from last month".

Patterns ("Fridays are order-in") are derived by a scheduled job over
`get_orders` history, in code. Not by asking a model to notice things.

**Done when** it puts your brand of milk in the cart without being told, and can
say which store that came from.

**You learn** memory architecture, and the more useful half — where RAG is the
wrong tool.

---

## 7 — Dedup, the nudge, and real money

An idempotency key per `(group, date, meal, surface)`. Read-before-write against
both the local ledger and Swiggy's `get_food_orders` / `get_booking_status`.

When someone asks again, a model judges "new order or amendment" — and that
judgement goes to the group as a question, never straight to an action. The
17:30 nudge is the same `interrupt()` built in phase 4.

**Done when** two people asking for dinner produces one order and one question,
and a retry storm produces zero duplicates.

**You learn** side-effect safety — the part that decides whether anyone trusts
it with a card.

---

## 8 — Make it someone else's

Langfuse traces, structured logs, a `.env.example` listing every knob, a README
where setup is `docker compose up` plus one browser visit, and the demo video
Swiggy asks for before granting production access.

**Open question to resolve in phase 2:** Swiggy grants production access per
developer. If every user needs their own OAuth client, "clone and run" has a gate
in the middle. Worth emailing `builders@swiggy.in` early.

**Done when** someone who is not you runs it against their own group and their
own credentials.

**You learn** observability, and the packaging discipline that separates a repo
from a product.
