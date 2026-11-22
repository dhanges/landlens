-- Q5: one village's yearly trend with YoY. Raw aggregation vs materialized view; refresh cost reported too.
-- variant: raw_aggregation
WITH s AS (
  SELECT p.village_id, p.land_type, extract(year FROM t.registered_on)::int AS yr,
         t.consideration_inr / t.area_sqm AS price_sqm
  FROM sale_transaction t JOIN parcel p USING (parcel_id) WHERE p.village_id = :vid)
SELECT village_id, land_type, yr, count(*) AS n_sales,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm) AS median_price_sqm,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)
         / lag(percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)) OVER w - 1 AS yoy
FROM s GROUP BY village_id, land_type, yr
WINDOW w AS (PARTITION BY village_id, land_type ORDER BY yr);
-- variant: materialized_view
SELECT village_id, land_type, yr, n_sales, median_price_sqm, yoy
FROM mv_village_price_index WHERE village_id = :vid ORDER BY land_type, yr;
-- refresh: mv_village_price_index
