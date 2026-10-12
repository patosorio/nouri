# Nouri v2

Conversational AI nutritionist and meal planning web app — FastAPI · Next.js 15 · Claude · pgvector

---

## What it is

Nouri is a plant-based meal planning app rebuilt around a conversational AI nutritionist and chef. Instead of filling out forms to get a meal plan, you talk to Nouri the way you'd talk to a real nutritionist — describe your goals, a craving, a training week, a dietary restriction — and it reasons, asks follow-ups, and acts.

One agent, four integrated capabilities:

- **Nutritionist** — conversational intake and ongoing dialogue. Understands diet type, goals, exclusions, and adapts from what you actually eat and accept over time.
- **Menu builder** — constructs full weekly or daily meal plans from the conversation, enforcing macro targets, protein variety, dietary rules, and your history.
- **Chef** — generates complete, cookable recipes on demand with ingredients, method, and timing. Expands saved recipes, suggests substitutions, talks technique.
- **Explainer** — on request, explains its own reasoning: why a week is balanced the way it is, what a specific recipe actually gives you nutritionally, and the science behind plant-based eating.

---

## Architecture

The core design principle: **agentic where autonomy earns its keep, deterministic where correctness must be guaranteed.**

The conversational agent handles dialogue, tool selection, recipe creativity, and nutritional explanations. Macro math, exclusion compliance, protein/ingredient variety, and raw/cooked ratio are enforced by pure Python validators — not by the model's memory of a prompt rule. The agent calls tools that return checked, structured results. It never writes to the database directly.

```
Next.js 15 (App Router)
    ↓ HTTPS + SSE (chat streaming) · Supabase Realtime (notifications)
FastAPI (async)
    ├── AI Agent Layer       — Anthropic SDK tool-use loop
    ├── Planner/Validator    — pure Python constraint enforcement + repair
    ├── Service Layer        — all DB reads/writes
    └── Background Worker   — async plan generation jobs
Supabase (PostgreSQL + pgvector + Auth + Realtime + RLS)
```

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), Tailwind CSS, shadcn/ui, TanStack Query v5 |
| Backend | FastAPI, Python 3.12, Pydantic V2, SQLAlchemy 2.0 async, asyncpg |
| AI | Anthropic Claude (Sonnet for agent + recipe gen, Haiku for structured tasks) |
| Embeddings | Voyage AI `voyage-3-lite` + pgvector for recipe semantic search |
| Database | Supabase (PostgreSQL 15, pgvector, Row-Level Security, Realtime) |
| Auth | Supabase Auth (JWT, RS256) |
| Hosting | GCP Cloud Run (API + worker), Vercel (frontend) |
| CI/CD | GCP Cloud Build |
| Payments | Stripe |

---

## Key features

- **Conversational meal planning** — chat to generate, refine, swap, and explain plans
- **Direct plan generation** — form-driven weekly/daily plan without needing a conversation
- **Juicing mode** — first-class juice slots with time-of-day, size, and colour configuration
- **Diet type + subtypes** — primary diet axis (vegan, WFPB, pescatarian, etc.) plus modifiers (keto, high-iron, anti-inflammatory, etc.)
- **Cooking type** — explicit raw/cooked ratio enforced deterministically at generation time
- **Recipe library** — semantic search over saved recipes, import from image or text, expand and riff on existing recipes
- **Nutritional profiling** — per-recipe macro breakdown and qualitative highlights on request
- **Shopping list** — auto-generated from a plan, diffed against pantry
- **Pantry tracking** — ingredient inventory that feeds into shopping list generation
- **Behaviour signals** — accept/swap/edit actions used as labelled quality data for eval
- **Async generation** — full weekly plans generated in the background with real-time notification on completion
- **Tier gating** — free and paid tiers with feature access enforced at the API and UI layers

---

## Project structure

```
nouri/
├── api/                   # FastAPI backend → GCP Cloud Run
│   ├── agent/             # AI orchestration layer
│   ├── validation/        # Deterministic constraint enforcement
│   ├── services/          # Domain logic + all DB writes
│   ├── routers/           # API route handlers
│   ├── db/                # SQLAlchemy models + Alembic migrations
│   └── worker/            # Background job processor
└── client/                # Next.js 15 frontend → Vercel
    ├── app/               # App Router routes
    ├── components/        # Shared + feature components
    ├── hooks/             # TanStack Query hooks
    └── lib/               # API client, Supabase client, SSE reader
```

---

## Local development

Local app data lives in Docker Postgres (pgvector). Auth stays on hosted Supabase — the API verifies JWTs against that project's JWKS. Compose does not run Next.js; the client runs on the host.

| Service | How | URL |
|---|---|---|
| Postgres 15 + pgvector | Compose `db` | `localhost:5432` (`nouri` / `nouri` / `nouri`) |
| FastAPI | Compose `api` | http://localhost:8000 (`/health` → `{"status":"ok"}`) |
| Background worker | Compose `worker` | polls `job_queue` (plan generation, nutrition) |
| Next.js | `npm run dev` in `client/` | http://localhost:3000 |
| Auth | hosted Supabase project | JWT + user lookup for seed |

### Prerequisites

- Docker Compose v2
- Node.js 20+ (Next.js 15)
- A Supabase project (Auth enabled) and its URL / anon key / service role key
- API keys for Anthropic and Voyage if you want live generation and embeddings (seeded UI works without them)

### 1. API environment

```bash
cp api/.env.example api/.env
```

Fill at least:

| Variable | Local value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://nouri:nouri@db:5432/nouri` |
| `SUPABASE_URL` | `https://<project>.supabase.co` (https URL only — not prefixed with `SUPABASE_URL=`) |
| `SUPABASE_SERVICE_ROLE_KEY` | service role key (worker + seed; never the client) |
| `SUPABASE_JWT_ISSUER` | `https://<project>.supabase.co/auth/v1` |
| `SUPABASE_JWT_PUBLIC_KEY` | required by settings; verification uses JWKS from `SUPABASE_URL` |
| `FIELD_ENCRYPTION_KEY` | 32-byte key, raw or base64 (see below) |
| `CORS_ORIGINS` | already includes `http://localhost:3000` in the example |
| `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY` | needed for chat, plan jobs, and recipe embeddings |
| `STRIPE_WEBHOOK_SECRET` | required by settings; unused until billing is wired |

Generate an encryption key:

```bash
python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Host-side tools (seed, alembic, pytest, local uvicorn) rewrite `@db:` → `@localhost:` when hostname `db` does not resolve. Inside Compose that rewrite is a no-op.

### 2. Client environment

Create `client/.env.local` (not committed):

```
NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Start API, worker, and database

From the repo root. `GIT_SHA` is passed into the api and worker containers by `docker-compose.override.yml`, so `worker_started` and `versions.code_version` show that sha. The worker image does not have `.git`.

```bash
GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d
```

`docker compose restart` does not reload the override. Use `up -d` after changing it. Compose maps API `8080` → host `8000`. Both `api` and `worker` bind-mount `./api`; rebuild when Python dependencies change.

Migrations are **not** applied on container start:

```bash
docker compose exec api alembic upgrade head
```

### 4. Start the client

```bash
cd client
npm install
npm run dev
```

Open http://localhost:3000. Sign up once so Supabase Auth has a user (seed looks that user up by email).

### 5. Seed demo data

Requires a migrated DB and that Auth user. Preferred (same network as the API container):

```bash
docker compose exec api python -m scripts.seed_demo_data \
  --email you@example.com --force
```

Host-side (venv, from `api/`):

```bash
python -m scripts.seed_demo_data --email you@example.com --force
```

`--force` wipes that user's app rows and reseeds: profile, exclusions, pantry, ~6 recipes, a reviewing plan, an approved plan, shopping list, a sample chat, notifications. Seed does **not** write `recipe_embeddings`, so plan-generation candidate search will not see those recipes until they are embedded.

### Optional: API on the host

With Compose `db` up and `api/.venv` installed from `api/requirements.txt`:

```bash
cd api
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
python -m worker.main
```

Use `DATABASE_URL` with `@localhost` (or keep `@db` and let `db/session.py` rewrite it).

### Tests

From `api/` (Postgres reachable; AI calls mocked in unit tests):

```bash
cd api
pytest tests/unit/
make golden
```

No step is accepted unless `make golden` passes.

`pytest.ini` excludes `-m eval` by default. Live evals: `pytest tests/evals/ -m eval`. Integration tests need the migrated local database. `make test` runs the full unit suite. `DATABASE_URL` and `TEST_DATABASE_URL` must point at `@localhost:5432` when those commands run on the Mac.

---

## Design system

Blue / white / coral palette (`--color-primary` `#4980DA`, `--color-bg` `#D3E4F4`, `--color-cta` `#F45B63`) with Instrument Sans (display) and DM Mono (labels + stats). Tokens: `docs/0_BRAND_AND_DOMAIN_SPEC_V2.md`.

---

## Status

Active development — V1 in progress. Plan generation uses a greedy slot assigner after one LLM pool call. A valid JWT creates `auth.users` + `user_profiles` stubs so chat can insert. Apply `alembic upgrade head` (includes RLS migration 002).
