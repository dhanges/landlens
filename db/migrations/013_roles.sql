-- 013: least-privilege roles (spec 2.10, DEC-004). Schema phase (runs after 001-009).
-- landlens_owner is the compose bootstrap user (POSTGRES_USER) and owns every object; it is not created here.
-- Roles are created without passwords; `landlens migrate` sets them from LANDLENS_API_PASSWORD and
-- LANDLENS_TILES_PASSWORD, so no secret ever lives in a migration file.
-- Grants on views (011) and tile functions (012) are made in those migrations.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'landlens_api') THEN
    CREATE ROLE landlens_api LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'landlens_tiles') THEN
    CREATE ROLE landlens_tiles LOGIN;
  END IF;
END $$;

DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO landlens_api, landlens_tiles', current_database());
END $$;
GRANT USAGE ON SCHEMA public TO landlens_api, landlens_tiles;

-- landlens_api: read and write app tables, never alter schema (no CREATE on the schema, owns nothing).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO landlens_api;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO landlens_api;
ALTER DEFAULT PRIVILEGES FOR ROLE landlens_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO landlens_api;
ALTER DEFAULT PRIVILEGES FOR ROLE landlens_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO landlens_api;
-- credit_ledger is append-only: the API may insert and read, never rewrite history.
REVOKE UPDATE, DELETE ON credit_ledger FROM landlens_api;

-- landlens_tiles (Martin): SELECT only on the base tables the tile functions read (spec 2.10) plus
-- parcel_coverage for the DEC-004 tiles_coverage source. Nothing else: no users, no ledger.
GRANT SELECT ON parcel, village, plan_zone, dev_project, project_status_history, infra_feature, parcel_coverage
  TO landlens_tiles;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
