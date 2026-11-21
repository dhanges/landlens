-- Migration 001: extensions (spec 2.4, DEC-004 / OQ-32).
-- Applied by `landlens migrate` (spec 2.17) as landlens_owner.
-- Idempotent: the M0 init script (db/initdb/00_extensions.sql) already created these,
-- so IF NOT EXISTS makes re-application a no-op.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
