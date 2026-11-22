-- 007: business tables (spec 2.4 group 7, ADR-010). Schema phase.
-- Delete rules (spec 2.5, DEC-004): report_unlock.parcel_id and every FK on credit_ledger keep the
-- default NO ACTION; report_unlock.user_id and both watchlist FKs cascade.

CREATE TABLE app_user (
  user_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email          text NOT NULL,
  password_hash  text NOT NULL,
  credit_balance integer NOT NULL DEFAULT 0 CHECK (credit_balance >= 0),
  created_at     timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX app_user_email_uq ON app_user (lower(email));

CREATE TABLE credit_ledger (                 -- append-only
  entry_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id         bigint NOT NULL REFERENCES app_user,
  delta           integer NOT NULL CHECK (delta <> 0),
  reason          ledger_reason NOT NULL,
  parcel_id       bigint REFERENCES parcel,
  idempotency_key uuid UNIQUE,
  created_at      timestamptz NOT NULL DEFAULT now());

CREATE TABLE report_unlock (
  user_id       bigint REFERENCES app_user ON DELETE CASCADE,
  parcel_id     bigint REFERENCES parcel,
  unlocked_at   timestamptz NOT NULL DEFAULT now(),
  credits_spent integer NOT NULL CHECK (credits_spent >= 0),
  PRIMARY KEY (user_id, parcel_id));         -- double charge impossible

CREATE TABLE watchlist (
  user_id   bigint REFERENCES app_user ON DELETE CASCADE,
  parcel_id bigint REFERENCES parcel   ON DELETE CASCADE,
  added_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, parcel_id));
