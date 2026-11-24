-- 015: price spread for the trends page (post-load phase, migrate.POST_LOAD).
-- Adds p25_price_sqm and p75_price_sqm (percentile_cont, like the median) to mv_village_price_index and
-- mv_mandal_price_index. A materialized view cannot gain columns in place, so both are recreated with the same
-- unique indexes (REFRESH ... CONCURRENTLY needs them) and grants. mv_parcel_metrics reads
-- mv_village_price_index, so it is dropped by the CASCADE and recreated from its own saved definition and index
-- definitions (taken from the catalog, so 011's SQL is not duplicated here and cannot drift).

CREATE TEMP TABLE _pm_saved ON COMMIT DROP AS
SELECT pg_get_viewdef('mv_parcel_metrics'::regclass, true) AS def,
       array(SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'mv_parcel_metrics') AS idx;

DROP MATERIALIZED VIEW mv_village_price_index CASCADE;     -- also drops mv_parcel_metrics
DROP MATERIALIZED VIEW mv_mandal_price_index;

CREATE MATERIALIZED VIEW mv_village_price_index AS
WITH s AS (
  SELECT p.village_id, p.land_type,
         extract(year FROM t.registered_on)::int AS yr,
         t.consideration_inr / t.area_sqm       AS price_sqm
  FROM sale_transaction t JOIN parcel p USING (parcel_id))
SELECT village_id, land_type, yr,
       count(*) AS n_sales,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm) AS median_price_sqm,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)
         / lag(percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)) OVER w - 1 AS yoy,
       percentile_cont(0.25) WITHIN GROUP (ORDER BY price_sqm) AS p25_price_sqm,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY price_sqm) AS p75_price_sqm
FROM s
GROUP BY village_id, land_type, yr
WINDOW w AS (PARTITION BY village_id, land_type ORDER BY yr);
CREATE UNIQUE INDEX ON mv_village_price_index (village_id, land_type, yr);  -- required for CONCURRENTLY

CREATE MATERIALIZED VIEW mv_mandal_price_index AS
WITH s AS (
  SELECT v.mandal_id, p.land_type,
         extract(year FROM t.registered_on)::int AS yr,
         t.consideration_inr / t.area_sqm       AS price_sqm
  FROM sale_transaction t JOIN parcel p USING (parcel_id) JOIN village v USING (village_id))
SELECT mandal_id, land_type, yr,
       count(*) AS n_sales,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm) AS median_price_sqm,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)
         / lag(percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)) OVER w - 1 AS yoy,
       percentile_cont(0.25) WITHIN GROUP (ORDER BY price_sqm) AS p25_price_sqm,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY price_sqm) AS p75_price_sqm
FROM s
GROUP BY mandal_id, land_type, yr
WINDOW w AS (PARTITION BY mandal_id, land_type ORDER BY yr);
CREATE UNIQUE INDEX ON mv_mandal_price_index (mandal_id, land_type, yr);

DO $$
DECLARE
  saved record;
  ix text;
BEGIN
  SELECT * INTO saved FROM _pm_saved;
  EXECUTE 'CREATE MATERIALIZED VIEW mv_parcel_metrics AS ' || saved.def;
  FOREACH ix IN ARRAY saved.idx LOOP
    EXECUTE ix;
  END LOOP;
END $$;

GRANT SELECT ON mv_parcel_metrics, mv_village_price_index TO landlens_tiles;
GRANT SELECT ON mv_parcel_metrics, mv_village_price_index, mv_mandal_price_index TO landlens_api;
ANALYZE mv_village_price_index;
ANALYZE mv_mandal_price_index;
ANALYZE mv_parcel_metrics;
