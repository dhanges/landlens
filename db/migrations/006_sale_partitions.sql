-- 006: yearly partitions of sale_transaction, 2010 to 2027, plus DEFAULT (spec 2.4, 2.8, ADR-006).
-- Schema phase. `landlens partitions` creates later years ahead of time.

DO $$
DECLARE y int;
BEGIN
  FOR y IN 2010..2027 LOOP
    EXECUTE format(
      'CREATE TABLE sale_transaction_%s PARTITION OF sale_transaction FOR VALUES FROM (%L) TO (%L)',
      y, make_date(y, 1, 1), make_date(y + 1, 1, 1));
  END LOOP;
END $$;

CREATE TABLE sale_transaction_default PARTITION OF sale_transaction DEFAULT;
