-- 005: prices (spec 2.4 group 6). Schema phase.
-- Delete rules (spec 2.5, DEC-004): guideline_rate.village_id and every FK on sale_transaction keep the
-- default NO ACTION (behaves like RESTRICT here; no deferred constraints are used).

CREATE TABLE guideline_rate (
  village_id         integer REFERENCES village,
  land_class         land_type,
  effective_from     date,
  rate_inr_per_sqm   numeric(12,2) NOT NULL CHECK (rate_inr_per_sqm > 0),
  source             data_source NOT NULL,
  PRIMARY KEY (village_id, land_class, effective_from));

CREATE SEQUENCE sale_txn_seq;
CREATE TABLE sale_transaction (
  txn_id            bigint NOT NULL DEFAULT nextval('sale_txn_seq'),
  registered_on     date   NOT NULL,
  parcel_id         bigint NOT NULL REFERENCES parcel,
  consideration_inr numeric(14,2) NOT NULL CHECK (consideration_inr > 0),
  area_sqm          numeric(12,2) NOT NULL CHECK (area_sqm > 0),   -- partial sales happen
  doc_no            text NOT NULL,
  source            data_source NOT NULL DEFAULT 'synthetic',
  PRIMARY KEY (txn_id, registered_on)         -- must include the partition key
) PARTITION BY RANGE (registered_on);
