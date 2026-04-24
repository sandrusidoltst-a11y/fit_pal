# FitPal Coach Dashboard — PRD

_Last updated: 2026-04-24_

---

## 1. Executive Summary

FitPal Coach Dashboard is a web companion to the FitPal Telegram bot. The bot is where trainees log food in natural language; the dashboard is where the coach sees what that log actually looks like against the plan. It turns *"I wonder if my trainees are following their plan"* into *"I know in 10 seconds, and I know who needs a check-in today."*

The MVP is single-coach (Dolev) with a handful of real trainees. The goal is to validate that a real-time, at-a-glance view of daily intake + body progress actually changes how the coach coaches — earlier interventions, better conversations, fewer trainees slipping through unnoticed.

**Success criterion for V1:** after four weeks of daily use, the coach has a clear answer to the question *"does seeing this data change how I coach?"* — proving (or disproving) the thesis behind the product before scaling.

---

## ⚠️ About the Decisions in This Document

This PRD is a **structural scaffold**, not a set of committed decisions.

Most of the choices here — framework selections, directory structure, auth approach, API conventions, phase ordering, table/field assumptions — are **defaults Claude proposed** during the PRD conversation. They were accepted to keep the document moving, not because they've been evaluated in depth.

**Before each implementation phase, the relevant decisions must be re-opened and discussed.** Specifically:

- Tech stack choices (Tailwind, TanStack Query, React Router, Recharts) — accepted as defaults; open to revisit.
- Architectural specifics (frontend hosting model, auth middleware placement, coach-scoping enforcement layer, REST vs other API style) — accepted as defaults; must be planned before building.
- Data model additions (macro targets, coach-trainee relationship, photo attachments) — acknowledged as requirements; exact schema is an implementation decision.
- Phase sequencing — a proposal; may reshuffle based on dependency order once planning starts.

The PRD defines **what we're building and why**. Each `/plan-feature` session before a phase starts defines **how**.

---

## 2. Mission

Give the coach one surface that answers *who's on track, who's drifting, and who needs my attention today* — without spreadsheets, without interrogating the trainee, and without waiting until the next session.

### Core Principles

1. **Coach-first** — every screen is designed around a coach's workflow, not a generic admin UI.
2. **At-a-glance over click-through** — compliance and plan deviation surface in the list view; the detail view is for diagnosis.
3. **Single source of truth** — daily intake, plan, and body metrics all live together.
4. **Mostly read-only** — V1 is observation plus plan upload and food catalog editing. No messaging, no inline plan editing.
5. **Multi-coach ready** — data model and auth support multiple coaches from day one, even though only one launches with it.
6. **Privacy by default** — a coach only ever sees trainees assigned to them. Enforced as a non-negotiable architectural principle; exact enforcement layer decided at implementation time.

---

## 3. Target Users

### Primary: The Coach

- **V1**: Dolev — sole coach, 3–5 real trainees (brother, friends, potentially one gym contact).
- **V2+**: other fitness/nutrition coaches, each with their own method and 5–20 trainees.
- Tech comfort: comfortable with web UIs; not expected to touch code or databases.
- Access pattern: checks in daily, not continuously — quick glances to spot issues, deeper dives when something looks off.

### Indirect: Trainees

- Do not use the dashboard.
- Interact with FitPal only through the Telegram bot (log food, respond to HITL, read coach responses).
- Their logging behavior is the data source the dashboard depends on. If they don't log, the dashboard is empty.

### Access Model

- **V1**: single coach, simple auth for the deployed version.
- **V2+**: multi-coach with strict isolation — every query scoped by `coach_id`; a coach never sees another coach's trainees.

---

## 4. MVP Scope

### In Scope (✅)

**Screens**
- Trainee List — search, sort, 7-day compliance strip, today's calories and protein at a glance.
- Trainee Detail — header, 4 KPIs, food log (no fat column), Body Stats panel, Macros-vs-Plan with Day / Week / Month scope + Grams/Servings toggle.
- Plan upload + view (dedicated route or modal per trainee).
- Food catalog editor — list, search, edit macros/category/tag/serving, add new food.

**Data & Logic**
- Read-only view of food logs (today + historical).
- 7-day compliance percentage + per-day dot strip (configurable threshold, default ±10% across calories, protein, carbs).
- Week view = grouped bar chart per day; Month view = heatmap.
- Body stats — weight trend + 7-day delta (waist deferred as a feature; column added whenever it lands).
- Progress photos — dashboard renders them when present; bot-side upload flow is a deferred FitPal feature, not dashboard work.
- Client-side pattern notes (weekend-slip, over-calories, low-protein).

**Infrastructure**
- Coach authentication via Supabase Auth (email/password, JWT).
- Every query scoped to the authenticated coach's trainees.
- Dark mode only, English UI, desktop-first.
- Deployed to Railway alongside existing services (exact hosting model decided at implementation time).

### Out of Scope (❌) — deferred to V2+

- Alerts / notifications of any kind.
- Inline plan editor (V1 = upload file + enter targets via form; no editing in dashboard).
- Trainee invite / onboarding from dashboard.
- Coach → trainee messaging from dashboard.
- Trainee-facing views or portals (if ever built, would be a separate dashboard).
- PDF / email reports for trainees.
- Hebrew UI.
- Mobile layout.
- Light mode.
- Real-time updates (polling or manual refresh is fine).
- LLM-generated insights or summaries.
- Cross-trainee activity feed.

### Known Dependencies

1. **Structured macro targets** — compliance math requires numeric daily targets per trainee, differentiated by training vs rest day. Currently only `user_profiles.nutrition_plan` (text) exists. Must be added before compliance renders meaningfully.
2. **Coach-trainee relationship** — `user_profiles` must identify which coach owns each trainee.
3. **Photo attachments on body stats** — dashboard is built to display photos; bot-side upload flow is a deferred FitPal feature. Photos will render empty until that ships.

---

## 5. User Stories

1. As a coach, I want to see a list of all my trainees at a glance, so I can spot who needs attention today.
2. As a coach, I want each trainee's row to show today's calories and protein relative to target, so I can identify drift without clicking.
3. As a coach, I want a 7-day compliance indicator per trainee, so I can find trainees slipping over longer periods.
4. As a coach, I want to click into a trainee to see exactly what they ate today with macros per entry, so I can diagnose compliance in context.
5. As a coach, I want to see macros-vs-plan across Day / Week / Month views, so I can spot patterns (weekend slips, chronic over-calories, low-protein streaks).
6. As a coach, I want to see body stats (weight) and progress photos over time, so I can correlate nutrition with physical change.
7. As a coach, I want to upload a nutrition plan as a text file and enter the trainee's macro targets via form, so I don't have to touch the CLI or the DB.
8. As a coach, I want to edit the food catalog (macros, category, serving size) from the dashboard, so I can tune the catalog without opening Supabase.
9. As a coach, I can only see my own trainees' data — no other coach's data is ever visible to me.

---

## 6. Architecture

*Defaults proposed by Claude — revisit during implementation planning.*

### High-level architecture

```
┌─────────────┐   HTTPS   ┌──────────────────────────────┐
│  Browser    │ ────────► │  Dashboard Frontend          │
│  (Coach)    │           │  React + Vite + Tailwind     │
└─────────────┘           └─────────┬────────────────────┘
                                    │ fetch
                                    ▼
                          ┌──────────────────────────────┐
                          │  FastAPI (src/)              │
                          │  ├─ existing bot endpoints   │
                          │  └─ NEW: /api/dashboard/*    │
                          │      (coach-scoped routes)   │
                          └─────────┬────────────────────┘
                                    │ asyncpg
                                    ▼
                          ┌──────────────────────────────┐
                          │  Supabase Postgres           │
                          │  (existing + new fields)     │
                          └──────────────────────────────┘
                                    ▲
                                    │ Telegram webhook
                          ┌──────────────────────────────┐
                          │  aiogram bot (bot/gateway.py)│
                          └──────────────────────────────┘
```

### Directory structure (proposed)

```
fit_pal/
├── src/                    # existing LangGraph backend
│   ├── agents/             # unchanged
│   ├── services/           # existing services reused; new ones added where needed
│   ├── dashboard/          # NEW — dashboard API layer
│   │   ├── routes/         # trainees, logs, plans, foods, auth
│   │   └── middleware.py   # coach-scoping middleware
│   ├── models.py           # existing + new models
│   └── security/           # existing auth middleware extended
├── bot/                    # existing, unchanged
├── dashboard/              # NEW — frontend
│   ├── src/
│   │   ├── screens/        # list, detail, plan upload, foods
│   │   ├── components/     # ported design primitives
│   │   ├── api/            # typed client for /api/dashboard/*
│   │   ├── hooks/          # useTrainees, useTraineeDetail, etc.
│   │   └── styles/         # tailwind.config.ts + design tokens
│   └── package.json
└── Dockerfile.dashboard    # if frontend hosting splits later
```

### Key patterns (proposed)

- **Shared service layer** — dashboard and bot reuse `src/services/*`. Only genuinely new domains (e.g. structured macro targets) get new services.
- **Coach-scoping is non-negotiable** — every dashboard endpoint is scoped to the authenticated coach. The specific enforcement layer (middleware, RLS, both) is an implementation decision.
- **Frontend talks to one API** — `/api/dashboard/*` under the same FastAPI service. Hosting model (shared origin vs split) is an implementation decision.
- **Server state via TanStack Query** — caching, background refetch, stale-while-revalidate.
- **Auth via Supabase** — coach logs in with email/password; JWT sent as Bearer token; middleware validates and injects `coach_id`.

---

## 7. Tech Stack

*Defaults proposed by Claude — revisit during implementation planning.*

### Backend (extends existing)

- Python 3.13+, FastAPI, SQLAlchemy 2.x (asyncpg), Pydantic v2 — all existing.
- **Supabase Auth** for coach login.
- **Supabase Storage** for progress photos (bucket provisioned now; bot upload deferred).
- Structlog, uv — existing.

### Frontend (new)

- **React 18** + **TypeScript**.
- **Vite** — build tool.
- **Tailwind CSS** — utility-first styling; tokens ported from the Claude Design prototype.
- **TanStack Query** — server state.
- **React Router** — routing.
- **Recharts** — charts (or hand-rolled SVG if Recharts feels heavy).

### Design system origin

- **Look** (colors, fonts, component visual design) comes from the Claude Design prototype.
- **Stack** (TypeScript, Vite, Tailwind, TanStack Query, Router) is standard production React — chosen to productionize the prototype's look, not copy its internal structure.

### Infrastructure

- Supabase Postgres (existing) + new Storage bucket for progress photos.
- Railway deployment (existing pipeline extended).
- Docker (extends existing pattern).
- GitHub Actions CI/CD — extend existing `ci.yml` to lint + typecheck the dashboard.

> **Needs further discussion:** infrastructure topology (shared vs split service, separate vs combined Railway deploy, domain/subdomain strategy). Revisit before Phase 5.

---

## 8. Data Model

*Defaults proposed by Claude — revisit during implementation planning.*

The dashboard reads and writes through the **existing Supabase Postgres DB**. Data flows are shared with the bot (same tables, same services).

### New data needs introduced by the dashboard

1. **Structured macro targets** — today only `user_profiles.nutrition_plan` (narrative text) exists. Compliance math requires numeric daily targets per trainee, differentiated by training vs rest day. A new structured model is required.

2. **Coach-trainee relationship** — `user_profiles` has no notion of which coach owns a trainee. A scoping field is required to support multi-coach isolation and to enforce the coach-only-sees-their-own-trainees rule.

3. **Photo attachments on body stats** — `personal_stats_log` tracks weight and body fat % but has no photo field. Bot-side upload is a planned FitPal feature; the dashboard must render available photos when they exist.

### Out of scope for the PRD

Exact schema changes — column names, types, indexes, FK constraints, RLS policies — are decided during implementation planning. The PRD names the *data requirements*; the plan names the *columns*.

---

## 9. Implementation Phases

*Defaults proposed by Claude — revisit during implementation planning.*

Five phases. Each phase delivers something demo-able before moving to the next.

### Phase 1 — Foundation

*Data model + scaffolding. Nothing visible yet.*

- Schema migrations (structured macro targets, coach-trainee relationship field, photo URL on body stats).
- Service-layer additions for new data domains.
- Seed Dolev as the V1 coach.
- `src/dashboard/` skeleton: routes package, middleware, auth scaffolding.

### Phase 2 — Design Import + Frontend Scaffold

*Bring the prototype into the codebase.*

- Scaffold `dashboard/` (Vite + React + TypeScript + Tailwind + React Router + TanStack Query).
- Port design tokens from the Claude Design prototype (colors, fonts, spacing) into `tailwind.config.ts`.
- Port component primitives pixel-perfect (Avatar, MiniBar, ComplianceStrip, CategoryPill, MacroBar, GroupedBarChart, Segmented, etc.).
- Build static versions of List and Detail screens with mock data — no API yet.
- **Deliverable:** the frontend looks exactly like the prototype, running locally against mock data.

### Phase 3 — Wire to Real Data (Core Read Path)

*First real-data demo surface.*

- Coach auth: login screen, JWT storage, protected routes.
- Dashboard API endpoints: list trainees, trainee detail, today's log, latest stats.
- Swap mock data for real API calls via TanStack Query.
- Compliance computation from structured macro targets + daily logs.

### Phase 4 — Advanced Views + Write Paths

*Feature-complete for V1.*

- Week and Month views (grouped bar chart + heatmap).
- Plan upload flow: file + macro targets form.
- Food catalog editor: list, search, edit, add.
- Client-side pattern notes.

### Phase 5 — Polish + Deploy

*Ship it.*

- Railway deployment (decide hosting model — see Architecture open question).
- CI: lint, typecheck, basic E2E smoke.
- CD: Docker build + Railway redeploy on merge.
- Demo polish: loading states, empty states, error boundaries.
- End-to-end smoke test: log in → list → detail → upload plan → edit a food.

---

## Related Documents

- [PRD.md](PRD.md) — FitPal bot/agent PRD
- [brain/GOALS.md](brain/GOALS.md) — project goals and mid-May POC deadline
- [Claude Design handoff bundle](https://api.anthropic.com/v1/design/h/5RDIo341ix8M7SdgFC4wcw) — source for visual design and component structure
