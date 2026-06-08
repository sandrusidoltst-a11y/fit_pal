-- Migration: dashboard_phase1_foundation
-- Coach Dashboard Phase 1 (Foundation) — additive, non-destructive.
--
-- Apply via the Supabase MCP server (mcp__supabase__apply_migration with name
-- "dashboard_phase1_foundation") or `supabase db push`. See
-- docs/plans/dashboard-phase-1-foundation.md (Tasks 1-3) for verification queries.
--
-- PRE-FLIGHT: confirm the V1 coach exists before the backfill below:
--   SELECT id, email FROM auth.users
--   WHERE id = '71a8c873-c6bd-498e-a6ca-bd27d6118329';  -- expect 275939731@telegram.fitpal.bot

-- 1. Coach ownership on user_profiles (nullable, then backfill to the single V1 coach)
ALTER TABLE user_profiles ADD COLUMN coach_id UUID;
UPDATE user_profiles SET coach_id = '71a8c873-c6bd-498e-a6ca-bd27d6118329' WHERE coach_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_profiles_coach_id ON user_profiles (coach_id);
ALTER TABLE user_profiles
  ADD CONSTRAINT fk_user_profiles_coach_id
  FOREIGN KEY (coach_id) REFERENCES auth.users(id) ON DELETE SET NULL;

-- 2. Progress-photo URL on personal_stats_log (bot upload flow ships later)
ALTER TABLE personal_stats_log ADD COLUMN photo_url TEXT;

-- 3. Structured macro targets (per trainee, per day_type)
CREATE TABLE macro_targets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,                               -- the trainee
  day_type TEXT NOT NULL CHECK (day_type IN ('training','rest')),
  calories DOUBLE PRECISION NOT NULL,
  protein_g DOUBLE PRECISION NOT NULL,
  carbs_g DOUBLE PRECISION NOT NULL,
  fat_g DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ,
  CONSTRAINT uq_macro_targets_user_day_type UNIQUE (user_id, day_type)
);
CREATE INDEX idx_macro_targets_user_id ON macro_targets (user_id);
ALTER TABLE macro_targets
  ADD CONSTRAINT fk_macro_targets_user_id
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- RLS (defense-in-depth; app-layer remains primary enforcement per ADR-0001)
ALTER TABLE macro_targets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON macro_targets
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated users can read" ON macro_targets
  AS PERMISSIVE FOR SELECT TO authenticated USING (true);
