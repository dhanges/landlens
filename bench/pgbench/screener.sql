-- pgbench script (spec 2.19): the screener's page-1 query (Q6, covering index I5 pm_screener_ix) with a random
-- 5-year growth threshold per transaction. Run by scripts/pgbench_screener.sh at 8 and 32 clients.
\set c random(5, 18)
SELECT parcel_id, village_id, land_type, zone_code, area_sqm, price_sqm, cagr_5y, nearest_active_project_m
FROM mv_parcel_metrics
WHERE land_type = 'peri_urban' AND nearest_active_project_m <= 3000 AND cagr_5y >= :c / 100.0
ORDER BY cagr_5y DESC, parcel_id DESC
LIMIT 50;
