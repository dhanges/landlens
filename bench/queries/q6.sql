-- Q6: screener, 5 filters, page 1 and page 50 (spec 2.8). Base joins vs MV vs MV + covering index (I5);
-- OFFSET vs keyset at page 50. Median and p95.
-- M2 fix: selective-filter variants, with min CAGR raised to the 99th percentile of the matching rows
-- (:scr_sel_min_cagr, computed by the runner), so fewer rows qualify than fit on a page and the planner can no
-- longer stop a top-N scan early; with and without I5.
-- variant: base_joins_page1
WITH asof AS (SELECT landlens_as_of() AS d),
active AS (SELECT j.project_id, j.geom FROM dev_project j
           WHERE (SELECT h.status FROM project_status_history h, asof WHERE h.project_id = j.project_id
                  AND h.effective_from <= asof.d ORDER BY h.effective_from DESC LIMIT 1)
                 IN ('sanctioned', 'under_construction')),
med AS (SELECT p.village_id, p.land_type, extract(year FROM t.registered_on)::int AS yr,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY t.consideration_inr / t.area_sqm) AS m
        FROM sale_transaction t JOIN parcel p USING (parcel_id) GROUP BY 1, 2, 3),
ly AS (SELECT village_id, land_type, max(yr) AS y FROM med, asof WHERE yr <= extract(year FROM asof.d) GROUP BY 1, 2),
cagr AS (SELECT ly.village_id, ly.land_type, power(c.m / b.m, 1.0 / (ly.y - b.yr)) - 1 AS cagr_5y
         FROM ly JOIN med c ON (c.village_id, c.land_type, c.yr) = (ly.village_id, ly.land_type, ly.y)
         JOIN LATERAL (SELECT yr, m FROM med i WHERE (i.village_id, i.land_type) = (ly.village_id, ly.land_type)
                       AND i.yr BETWEEN ly.y - 6 AND ly.y - 4 ORDER BY abs(i.yr - (ly.y - 5)), i.yr LIMIT 1) b ON true),
gw AS (SELECT DISTINCT ON (mandal_id) mandal_id, category FROM gw_assessment ORDER BY mandal_id, assessment_year DESC),
m AS (SELECT p.parcel_id, v.name AS village_name, p.area_sqm, p.land_type, z.zone_code, ap.d AS nearest_active_project_m,
             c.cagr_5y, gw.category AS gw_category
      FROM parcel p JOIN village v USING (village_id)
      LEFT JOIN LATERAL (SELECT pl.zone_code FROM parcel_zone pz JOIN plan_zone pl USING (zone_id)
                         WHERE pz.parcel_id = p.parcel_id ORDER BY pz.overlap_pct DESC, pz.zone_id LIMIT 1) z ON true
      LEFT JOIN LATERAL (SELECT ST_Distance(p.centroid, a.geom) AS d FROM active a ORDER BY 1 LIMIT 1) ap ON true
      LEFT JOIN cagr c ON (c.village_id, c.land_type) = (p.village_id, p.land_type)
      LEFT JOIN gw ON gw.mandal_id = v.mandal_id)
SELECT parcel_id, village_name, area_sqm, cagr_5y, nearest_active_project_m FROM m
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_min_cagr AND gw_category <> 'over_exploited'
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50;
-- variant: mv_no_covering_page1
-- setup: DROP INDEX pm_screener_ix
SELECT parcel_id, village_name, area_sqm, price_sqm, cagr_5y, nearest_active_project_m FROM mv_parcel_metrics
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_min_cagr AND gw_category <> 'over_exploited'
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50;
-- variant: mv_covering_page1
-- size: pm_screener_ix
SELECT parcel_id, village_name, area_sqm, price_sqm, cagr_5y, nearest_active_project_m FROM mv_parcel_metrics
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_min_cagr AND gw_category <> 'over_exploited'
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50;
-- variant: mv_covering_page50_offset
SELECT parcel_id, village_name, area_sqm, price_sqm, cagr_5y, nearest_active_project_m FROM mv_parcel_metrics
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_min_cagr AND gw_category <> 'over_exploited'
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50 OFFSET 2450;
-- variant: mv_covering_page50_keyset
SELECT parcel_id, village_name, area_sqm, price_sqm, cagr_5y, nearest_active_project_m FROM mv_parcel_metrics
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_min_cagr AND gw_category <> 'over_exploited'
  AND (cagr_5y, parcel_id) < (:scr_last_cagr, :scr_last_id)
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50;
-- variant: mv_no_covering_selective_page1
-- setup: DROP INDEX pm_screener_ix
SELECT parcel_id, village_name, area_sqm, price_sqm, cagr_5y, nearest_active_project_m FROM mv_parcel_metrics
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_sel_min_cagr AND gw_category <> 'over_exploited'
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50;
-- variant: mv_covering_selective_page1
-- size: pm_screener_ix
SELECT parcel_id, village_name, area_sqm, price_sqm, cagr_5y, nearest_active_project_m FROM mv_parcel_metrics
WHERE land_type = :scr_type AND zone_code = ANY(:scr_zones) AND nearest_active_project_m <= :scr_max_proj AND cagr_5y >= :scr_sel_min_cagr AND gw_category <> 'over_exploited'
ORDER BY cagr_5y DESC, parcel_id DESC LIMIT 50;
