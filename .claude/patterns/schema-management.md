# DB Schema Conventions

## What It Is

Every SQLAlchemy model in FitPal follows the same structural template: UUID primary key, `user_id` scoping column, timezone-aware timestamps, and optional audit columns. Production schema changes go through Supabase migrations — never through `create_all()` or `drop_all()`. FK constraints to Supabase-managed tables (`auth.users`) live in Postgres only, not in SQLAlchemy model definitions.

All models live in a single file: [src/models.py](../../src/models.py). There is no model-per-file split, no inheritance hierarchy beyond `Base`, and no abstract base models. Four models exist today: `FoodItem`, `DailyLog`, `UserProfile`, `PersonalStatsLog`. A fifth model follows the same template.

## The Model Template

Every new model starts from this shape:

```python
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Uuid, Float, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class NewTable(Base):
    __tablename__ = "new_table"

    # --- Primary key (always UUID) ---
    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)

    # --- User scoping (always present, usually NOT NULL) ---
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)

    # --- Domain columns ---
    # ... your columns here ...

    # --- Audit timestamps (add if rows will be updated) ---
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

Every piece of this template exists for a reason. The sections below explain each one.

## UUID Primary Keys

Every table uses `Uuid` primary keys with `uuid.uuid4` as the Python-side default:

```python
id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
```

Why UUIDs over auto-increment integers:

- **Universally unique across environments.** A `food_items` row created in dev, test, and prod will never collide on ID. This matters when debugging ("this row ID from the LangSmith trace — is it dev or prod?") and when seeding test data alongside real data in the same Supabase instance.
- **Safe for distributed writes.** The bot, the ETL script, and the graph server can all insert rows without coordinating on a sequence counter. `uuid4` is generated client-side with no DB round-trip.
- **No information leakage.** Auto-increment IDs reveal row counts and insertion order. UUIDs don't.

The `default=uuid_mod.uuid4` (no parentheses — it's the function, not a call) means SQLAlchemy calls `uuid4()` fresh on every insert. The ID is generated in Python before the INSERT statement, so it's available immediately on the model instance without needing a DB round-trip or `RETURNING` clause.

All four existing models follow this exactly. No exceptions.

## User Scoping: The `user_id` Column

Every user-facing table has a `user_id` column that ties rows to a Supabase auth user. The column is always `Uuid`, always indexed, and usually `NOT NULL`:

```python
# Standard: NOT NULL (user-scoped data)
user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)

# Exception: nullable (shared + user-created data coexist)
user_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, nullable=True, index=True)
```

The current models:

| Table | `user_id` nullable? | Why |
|---|---|---|
| `daily_logs` | NOT NULL | Every log entry belongs to exactly one user |
| `user_profiles` | NOT NULL + `unique=True` | One profile per user, always owned |
| `personal_stats_log` | NOT NULL | Every measurement belongs to exactly one user |
| `food_items` | **nullable** | System-wide foods (ETL-seeded) have `user_id=NULL`; user-created estimated foods have a `user_id` |

The default for a new table is **NOT NULL**. Make it nullable only if the table genuinely contains rows that aren't owned by any user (like the shared food database). Don't make it nullable "just in case" — that weakens the scoping guarantee and makes RLS policies harder to write.

The `index=True` is mandatory because almost every query filters by `user_id` (the tool-first pattern means every tool receives `user_id` and passes it to the service function's `WHERE` clause). Without the index, every user-scoped query is a full table scan.

`user_profiles` adds `unique=True` in addition to `index=True` because each auth user has exactly one profile. No other table has the unique constraint — users can have many logs, many stats, many foods.

## FK Constraints: Postgres-Only for `auth.users`

The FK relationship between `user_id` and `auth.users(id)` is enforced in Postgres via Supabase migrations, but is **not declared in the SQLAlchemy model**:

```python
# What we have — no ForeignKey reference:
user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)

# What we deliberately do NOT write:
user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, ForeignKey("auth.users.id"), nullable=False, index=True)
```

**Why:** The `auth.users` table is managed by Supabase — it's part of the `auth` schema, not our application schema, and it's not registered in our `Base.metadata`. If we added `ForeignKey("auth.users.id")` to the model, any code that calls `Base.metadata.create_all()` would fail:

```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 'daily_logs.user_id'
could not find table 'auth.users' with which to generate a foreign key
```

The constraint exists in Postgres and is enforced there — inserting a row with a `user_id` that doesn't exist in `auth.users` will fail with a FK violation. The enforcement is real; it just lives at the database level, not the ORM level.

**What we lose:** No `relationship()` navigation to `auth.users` (no `log.user` property). We never need this — `user_id` flows through `runtime.context.user_id` as a plain string, and we never join to `auth.users` from application code. The bot fetches user profiles via `user_profile_service`, not via ORM relationships.

**The CASCADE rules** (set in Supabase migrations, not in SQLAlchemy):

| Table | FK rule | Reason |
|---|---|---|
| `daily_logs.user_id` | `ON DELETE CASCADE` | If a user is deleted, their food logs are worthless |
| `user_profiles.user_id` | `ON DELETE CASCADE` | Profile belongs to the user entirely |
| `personal_stats_log.user_id` | `ON DELETE CASCADE` | Measurements belong to the user entirely |
| `food_items.user_id` | `ON DELETE SET NULL` | Estimated foods become "unowned" (still useful as shared foods) rather than being destroyed |

**FKs between our own tables** DO live in SQLAlchemy, because both sides are in `Base.metadata`:

```python
# daily_logs.food_id → food_items.id — this IS in the model
food_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, ForeignKey("food_items.id"), nullable=True)
```

The rule is simple: **FK to a table in our `Base.metadata` → put it in the model. FK to a Supabase-managed table (`auth.*`) → put it in a migration only.**

## Timestamp Columns

Three distinct timestamp patterns exist across the models. Each serves a different purpose and follows different rules.

### Event timestamps — "when did this happen"

```python
# DailyLog — when the user ate the food
timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

# PersonalStatsLog — when the user weighed themselves
recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
```

These represent **user-facing time** — set explicitly by application code (the node or tool passes the value), not auto-generated by SQLAlchemy or Postgres. They're indexed because date-range queries are the primary access pattern ("show me today's food log", "stats for the last week").

`DateTime(timezone=True)` maps to Postgres `TIMESTAMP WITH TIME ZONE` (`timestamptz`). Postgres stores everything as UTC internally and converts on display. This matters because users can be in different timezones — storing naive datetimes would make "12:00" ambiguous (noon in Tel Aviv or noon in New York?).

### Audit timestamps — "when was this row created/modified"

```python
created_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
)
updated_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True),
    onupdate=lambda: datetime.now(timezone.utc),
)
```

These are **system-managed** — application code never sets them directly:

- **`created_at`** uses `default=lambda: ...` — SQLAlchemy calls the lambda on every INSERT. Populated automatically; the code doesn't pass it in. It's typed `Optional` because it has a default, not because it should ever be NULL in practice.
- **`updated_at`** uses `onupdate=lambda: ...` — SQLAlchemy calls the lambda on every UPDATE (when the row changes and `.commit()` is called). Starts as `NULL` (row never updated) and gets populated on first update.

**Critical: the `lambda` is mandatory.** Without it:

```python
# WRONG — evaluates once at import time, every row gets the server start time
default=datetime.now(timezone.utc)

# CORRECT — evaluates fresh on every insert
default=lambda: datetime.now(timezone.utc)
```

This is a classic Python gotcha. Without the lambda, `datetime.now()` is called once when the module is imported and the resulting datetime object becomes a frozen default. Every row inserted for the lifetime of the process gets the same `created_at`.

### Which tables have audit columns

| Table | `created_at` | `updated_at` | Rationale |
|---|---|---|---|
| `DailyLog` | Yes | Yes | Rows can be corrected after logging |
| `UserProfile` | Yes | Yes | Profile gets updated (name, height, etc.) |
| `PersonalStatsLog` | Yes | No | Append-only time series — rows are never updated, only inserted |
| `FoodItem` | No | No | Seeded by ETL or created at commit time for estimated items; effectively immutable after creation |

**Default for a new table: include both `created_at` and `updated_at`.** Only omit them if you're certain the table is append-only (`PersonalStatsLog` pattern) or immutable (`FoodItem` pattern). When in doubt, add them — they cost one datetime per row and save hours when debugging "when did this row change?".

## Production Schema Changes: Supabase Migrations Only

**Never call `Base.metadata.create_all()` or `Base.metadata.drop_all()` against the production database.**

- `create_all()` creates tables that don't exist but **never alters existing ones**. If you add a column to a model, `create_all()` won't add it to the existing table. FitPal was burned by this: `daily_logs.food_id` was `NOT NULL` in the real table even though the model said `nullable=True`, because the table was created before the model was updated, and `create_all()` didn't notice. The Supabase migration corrected it.

- `drop_all()` drops every table. All data gone.

**What to do instead:** Create a Supabase migration (via the dashboard or MCP server) with explicit `ALTER TABLE` statements:

```sql
-- Example: adding a column
ALTER TABLE food_items ADD COLUMN source TEXT NOT NULL DEFAULT 'database';

-- Example: adding an FK constraint
ALTER TABLE daily_logs
ADD CONSTRAINT fk_daily_logs_user_id
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
```

Migrations are precise, reversible (you can write a down-migration), and preserve existing data. They're also version-controlled in Supabase's migration history, so you have a full audit trail of every schema change.

**Where `create_all()` still exists:** Only in the ETL script ([src/scripts/ingest_simple_db.py:76](../../src/scripts/ingest_simple_db.py#L76)), which uses a sync engine for bulk-seeding food data. The ETL script uses `DELETE FROM` (clears rows) rather than `drop_all()` (destroys tables) to reset data before re-seeding. This is deliberate — the table structure stays intact, only the rows are replaced.

## Cross-References

- **[tool-first.md](tool-first.md)** — service functions accept `session: AsyncSession` and perform the actual SQLAlchemy queries against these models. The `_serialize_*` helpers in tool wrappers convert ORM instances of these models to JSON-safe dicts. Understanding the model shapes helps understand what the serializers are flattening.
- **[async-patterns.md](async-patterns.md)** — the async engine (`asyncpg`) and `AsyncSession` are the runtime path for all model access. The sync engine (`psycopg2`) exists only for the ETL script.

## Rules

Hard rules. Violating any of these is a bug.

1. **Every new model gets a UUID primary key.** `mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)`. No auto-increment integers, no string IDs, no composite keys.

2. **Every user-facing table gets a `user_id: Mapped[...] = mapped_column(Uuid, ..., index=True)` column.** Default is `nullable=False`. Make it nullable only if the table genuinely contains shared/unowned rows.

3. **FK to `auth.users` lives in Postgres migrations only, not in SQLAlchemy models.** FK between our own tables (e.g. `daily_logs.food_id` → `food_items.id`) goes in the model.

4. **All timestamp columns use `DateTime(timezone=True)`.** No naive datetimes. Postgres stores them as UTC; the application passes timezone-aware datetimes.

5. **Audit timestamp defaults use `lambda:`, not bare expressions.** `default=lambda: datetime.now(timezone.utc)`, never `default=datetime.now(timezone.utc)`. Same for `onupdate`.

6. **New tables include `created_at` and `updated_at` by default.** Omit only if the table is provably append-only or immutable.

7. **Never `create_all()` or `drop_all()` against production.** Schema changes go through Supabase migrations with explicit `ALTER TABLE` statements.

8. **All models live in `src/models.py`.** No model-per-file split. Import `Base` from `src.models` when defining new models.

9. **Table names use `snake_case` plural.** `food_items`, `daily_logs`, `user_profiles`, `personal_stats_log`. Match the SQLAlchemy `__tablename__` to the Postgres table name exactly.
