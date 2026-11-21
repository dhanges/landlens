-- M0 extension bootstrap (DEC-004 / OQ-32).
-- Runs once at first cluster init as the owner role (POSTGRES_USER = landlens_owner),
-- before migration 001, which repeats this idempotently in M1 (spec 2.17).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
