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
├── docs/                  # All pre-development specifications
│   ├── 1_URS.md           # User Requirements Specification
│   ├── 2_SAD.md           # System Architecture Document
│   ├── 3_ERD.md           # Data Model / ERD + full DDL
│   ├── 4_API_DESIGN.yaml  # OpenAPI contract
│   ├── 5_SECURITY_ARCH.md # Security Architecture
│   ├── 6_DATA_INTEGRITY.md# Data Integrity Risk Assessment
│   ├── 7_TECH_SPEC.md     # Technical Specification
│   ├── 8_TEST_PLAN.md     # Test Plan
│   └── Design Files/      # Brand spec, screen mockups, component inventory
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

## Design system

Cream/sage/deep-green/terracotta palette with Instrument Sans (display + body) and DM Mono (labels + data). Full token reference in `docs/0_BRAND_AND_DOMAIN_SPEC_V2.md`.

---

## Status

Active development — V1 in progress.
