"""Public-schema PostgREST lock (0.58.1).

Empty RLS + FORCE + no grants to ``anon`` / ``authenticated``. The
backend connects as a table owner (postgres / bypassrls), so app
traffic is unaffected. Frontend uses Supabase Auth only — never
PostgREST table access.

``LOCK_PUBLIC_TABLES_SQL`` is the hook later revisions must run after
creating a public table. The Alembic-head pytest fails CI if any public
base table is missing ENABLE+FORCE.
"""

from __future__ import annotations

# Loops pg_tables so whatever is present at apply time is covered.
# ENABLE / FORCE are idempotent. No policies — empty forced RLS denies
# non-bypass roles.
LOCK_PUBLIC_TABLES_SQL = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
            r.tablename
        );
        EXECUTE format(
            'ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',
            r.tablename
        );
    END LOOP;
END
$$;
"""

# Roles exist on live Supabase; local / CI Postgres may not have them.
# Split per role so a missing name does not abort the other revoke.
REVOKE_POSTGREST_GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON TABLES FROM anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON SEQUENCES FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON TABLES FROM authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON SEQUENCES FROM authenticated;
    END IF;
END
$$;
"""

# Downgrade of the lock revision only. Re-GRANT to anon/authenticated is
# a deliberate ops step, not automatic.
UNLOCK_PUBLIC_TABLES_SQL = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY',
            r.tablename
        );
        EXECUTE format(
            'ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY',
            r.tablename
        );
    END LOOP;
END
$$;
"""

PUBLIC_RLS_STATUS_SQL = """
SELECT t.tablename, c.relrowsecurity, c.relforcerowsecurity
FROM pg_tables t
JOIN pg_namespace n ON n.nspname = t.schemaname
JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = t.tablename
WHERE t.schemaname = 'public'
  AND c.relkind = 'r'
ORDER BY t.tablename
"""

POSTGREST_TABLE_GRANTS_SQL = """
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND grantee IN ('anon', 'authenticated')
ORDER BY 1, 2, 3
"""
