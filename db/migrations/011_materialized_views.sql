-- 011: materialized views and I5 (spec 2.6), post-load phase.
-- mv_village_price_index exactly as in spec 2.6; mv_mandal_price_index per DEC-003 (OQ-20);
-- mv_parcel_metrics with the column list of spec 2.6 and the cagr_5y / soil_score formulas of DEC-003 (OQ-19).
-- "As of today" = landlens_as_of() (DEC-004, OQ-27).

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
         / lag(percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)) OVER w - 1 AS yoy
FROM s
GROUP BY village_id, land_type, yr
WINDOW w AS (PARTITION BY village_id, land_type ORDER BY yr);
CREATE UNIQUE INDEX ON mv_village_price_index (village_id, land_type, yr);  -- required for CONCURRENTLY

-- Mandal series computed from sales, since medians cannot be aggregated from village medians (DEC-003, OQ-20)
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
         / lag(percentile_cont(0.5) WITHIN GROUP (ORDER BY price_sqm)) OVER w - 1 AS yoy
FROM s
GROUP BY mandal_id, land_type, yr
WINDOW w AS (PARTITION BY mandal_id, land_type ORDER BY yr);
CREATE UNIQUE INDEX ON mv_mandal_price_index (mandal_id, land_type, yr);

CREATE MATERIALIZED VIEW mv_parcel_metrics AS
WITH asof AS (SELECT landlens_as_of() AS d),
active_project AS (       -- latest status as of d is sanctioned or under construction (spec 2.6)
  SELECT j.project_id, j.geom
  FROM dev_project j
  WHERE (SELECT h.status FROM project_status_history h, asof
         WHERE h.project_id = j.project_id AND h.effective_from <= asof.d
         ORDER BY h.effective_from DESC LIMIT 1) IN ('sanctioned', 'under_construction')),
last_sale AS (
  SELECT DISTINCT ON (t.parcel_id) t.parcel_id, t.consideration_inr / t.area_sqm AS price_sqm
  FROM sale_transaction t, asof
  WHERE t.registered_on <= asof.d
  ORDER BY t.parcel_id, t.registered_on DESC, t.txn_id DESC),
village_median AS (       -- median price per sq m over the last 36 months, per village and land type
  SELECT p.village_id, p.land_type,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY t.consideration_inr / t.area_sqm) AS med
  FROM sale_transaction t JOIN parcel p USING (parcel_id), asof
  WHERE t.registered_on > asof.d - interval '36 months' AND t.registered_on <= asof.d
  GROUP BY 1, 2),
latest_yr AS (
  SELECT i.village_id, i.land_type, max(i.yr) AS y
  FROM mv_village_price_index i, asof WHERE i.yr <= extract(year FROM asof.d)
  GROUP BY 1, 2),
cagr AS (                 -- DEC-003 (OQ-19): (median_Y / median_base)^(1/(Y-base)) - 1, base nearest Y-5 within +/-1
  SELECT ly.village_id, ly.land_type,
         power(cur.median_price_sqm / b.median_price_sqm, 1.0 / (ly.y - b.yr)) - 1 AS cagr_5y
  FROM latest_yr ly
  JOIN mv_village_price_index cur ON cur.village_id = ly.village_id AND cur.land_type = ly.land_type AND cur.yr = ly.y
  JOIN LATERAL (
    SELECT i.yr, i.median_price_sqm FROM mv_village_price_index i
    WHERE i.village_id = ly.village_id AND i.land_type = ly.land_type AND i.yr BETWEEN ly.y - 6 AND ly.y - 4
    ORDER BY abs(i.yr - (ly.y - 5)), i.yr LIMIT 1) b ON true),
gw AS (
  SELECT DISTINCT ON (mandal_id) mandal_id, category
  FROM gw_assessment ORDER BY mandal_id, assessment_year DESC),
guideline AS (
  SELECT DISTINCT ON (g.village_id, g.land_class) g.village_id, g.land_class, g.rate_inr_per_sqm
  FROM guideline_rate g, asof WHERE g.effective_from <= asof.d
  ORDER BY g.village_id, g.land_class, g.effective_from DESC)
SELECT p.parcel_id, p.village_id, v.name AS village_name, v.mandal_id, p.land_type, p.area_sqm, p.road_frontage_m,
       z.zone_code,
       ap.project_id                                     AS nearest_active_project_id,
       round(ap.dist::numeric, 1)                        AS nearest_active_project_m,
       round(hw.dist::numeric, 1)                        AS nearest_highway_m,
       round(wt.dist::numeric, 1)                        AS nearest_water_m,
       g.rate_inr_per_sqm                                AS guideline_rate_sqm,
       round(coalesce(ls.price_sqm, vm.med)::numeric, 2) AS price_sqm,
       round(vm.med::numeric, 2)                         AS village_median_sqm,
       round((100 * (coalesce(ls.price_sqm, vm.med) / nullif(vm.med, 0) - 1))::numeric, 2) AS price_vs_median_pct,
       round(c.cagr_5y::numeric, 4)                      AS cagr_5y,
       gw.category                                       AS gw_category,
       soil.score                                        AS soil_score
FROM parcel p
JOIN village v USING (village_id)
LEFT JOIN LATERAL (SELECT pl.zone_code FROM parcel_zone pz JOIN plan_zone pl USING (zone_id)
                   WHERE pz.parcel_id = p.parcel_id ORDER BY pz.overlap_pct DESC, pz.zone_id LIMIT 1) z ON true
LEFT JOIN LATERAL (SELECT a.project_id, ST_Distance(p.centroid, a.geom) AS dist FROM active_project a
                   ORDER BY ST_Distance(p.centroid, a.geom) LIMIT 1) ap ON true
LEFT JOIN LATERAL (SELECT ST_Distance(p.centroid, f.geom) AS dist FROM infra_feature f
                   WHERE f.feature_type IN ('national_highway', 'state_highway')
                   ORDER BY f.geom <-> p.centroid LIMIT 1) hw ON true
LEFT JOIN LATERAL (SELECT ST_Distance(p.centroid, f.geom) AS dist FROM infra_feature f
                   WHERE f.feature_type IN ('water_body', 'river')
                   ORDER BY f.geom <-> p.centroid LIMIT 1) wt ON true
LEFT JOIN LATERAL (       -- DEC-003 (OQ-19): inverse-distance-weighted 0-100 score of the nearest 3 samples
  SELECT round((sum(sc / greatest(d, 1)) / sum(1 / greatest(d, 1)))::numeric, 1) AS score
  FROM (SELECT ST_Distance(p.centroid, s.geom) AS d,
               (100 * (1 - least(abs(s.ph - 6.5) / 2.0, 1))
                + 100 * least(coalesce(s.organic_carbon_pct, 0) / 1.0, 1)
                + 100 * least(coalesce(s.n_kg_ha, 0) / 400.0, 1)
                + 100 * least(coalesce(s.p_kg_ha, 0) / 40.0, 1)
                + 100 * least(coalesce(s.k_kg_ha, 0) / 400.0, 1)) / 5 AS sc
        FROM soil_sample s ORDER BY s.geom <-> p.centroid LIMIT 3) n) soil ON true
LEFT JOIN last_sale ls ON ls.parcel_id = p.parcel_id
LEFT JOIN village_median vm ON vm.village_id = p.village_id AND vm.land_type = p.land_type
LEFT JOIN cagr c ON c.village_id = p.village_id AND c.land_type = p.land_type
LEFT JOIN gw ON gw.mandal_id = v.mandal_id
LEFT JOIN guideline g ON g.village_id = p.village_id AND g.land_class = p.land_type;

CREATE UNIQUE INDEX pm_parcel_uq ON mv_parcel_metrics (parcel_id);   -- required for CONCURRENTLY
CREATE INDEX pm_screener_ix ON mv_parcel_metrics (land_type, zone_code, cagr_5y DESC, parcel_id DESC)
  INCLUDE (price_sqm, nearest_active_project_m, area_sqm);           -- I5

-- grants on the objects this migration creates (spec 2.10)
GRANT SELECT ON mv_parcel_metrics, mv_village_price_index TO landlens_tiles;
GRANT SELECT ON mv_parcel_metrics, mv_village_price_index, mv_mandal_price_index TO landlens_api;
ANALYZE mv_parcel_metrics;
ANALYZE mv_village_price_index;
ANALYZE mv_mandal_price_index;
