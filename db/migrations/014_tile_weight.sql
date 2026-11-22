-- 014: lighter parcel and village tiles for the M4 map (spec 2.18 "only needed attributes", per-zoom simplification).
-- Post-load phase (migrate.POST_LOAD): the bodies read mv_parcel_metrics / mv_village_price_index from 011.
--
-- tiles_parcels was spec 2.8 verbatim: parcel_id, land_type, price_sqm and cagr_5y on every feature, 4096 extent.
-- The densest z14 tile at SF1 (14/11814/7360, 10,781 parcels) weighed 574 KB. Now:
--   * one attribute, h = heat class against the village median (price_vs_median_pct):
--       0 no price, 1 below (< -10%), 2 near (-10% .. +10%), 3 above (> +10%);
--   * z14: parcels simplified to half a pixel (2.4 m), extent 1024, and merged into one MultiPolygon per class,
--     so the per-feature overhead is paid 4 times, not 10,000 (146 KB). Parcels are 3 to 5 px wide at z14;
--     the map identifies a clicked parcel through GET /parcels/at, never from tile attributes;
--   * z15 and up: one feature per parcel, parcel_id as the MVT feature id (not a property), extent 4096 (117 KB
--     for the densest z15 tile).
-- tiles_villages also gains h (1..3: tercile of the village medians), so the style needs no data-dependent stops.

CREATE OR REPLACE FUNCTION tiles_parcels(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env),
  f AS (
    SELECT p.parcel_id, p.geom,
           CASE WHEN m.price_vs_median_pct IS NULL THEN 0
                WHEN m.price_vs_median_pct < -10 THEN 1
                WHEN m.price_vs_median_pct > 10 THEN 3
                ELSE 2 END AS h
    FROM b, parcel p JOIN mv_parcel_metrics m USING (parcel_id)
    WHERE z >= 14 AND p.geom && b.env),
  merged AS (
    SELECT h, ST_CollectionExtract(ST_Collect(g), 3) AS geom
    FROM (SELECT f.h, ST_AsMVTGeom(ST_Transform(ST_SimplifyPreserveTopology(f.geom, 2.4), 3857), b.env3857,
                                   1024, 64) AS g
          FROM f, b WHERE z = 14) s
    WHERE g IS NOT NULL GROUP BY h),
  single AS (
    SELECT f.parcel_id, f.h, ST_AsMVTGeom(ST_Transform(f.geom, 3857), b.env3857, 4096, 256) AS geom
    FROM f, b WHERE z >= 15)
  SELECT CASE WHEN z = 14 THEN (SELECT ST_AsMVT(merged, 'parcels', 1024, 'geom') FROM merged)
              ELSE (SELECT ST_AsMVT(single, 'parcels', 4096, 'geom', 'parcel_id') FROM single) END;
$$;

CREATE OR REPLACE FUNCTION tiles_villages(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env,
                    156543.0 / (2 ^ z) / 2 AS tol),
  med AS (
    SELECT v.village_id,
           (SELECT i.median_price_sqm FROM mv_village_price_index i
             WHERE i.village_id = v.village_id ORDER BY i.yr DESC, i.n_sales DESC LIMIT 1) AS median_price_sqm
    FROM village v),
  heat AS (
    SELECT village_id, median_price_sqm,
           CASE WHEN median_price_sqm IS NULL THEN 0 ELSE ntile(3) OVER (ORDER BY median_price_sqm) END AS h
    FROM med),
  mvt AS (
    SELECT v.village_id, v.name, v.mandal_id, v.boundary_source::text AS boundary_source,
           round(hh.median_price_sqm::numeric) AS median_price_sqm, hh.h,
           ST_AsMVTGeom(ST_Transform(ST_SimplifyPreserveTopology(v.geom, b.tol), 3857), b.env3857) AS geom
    FROM b, village v JOIN heat hh USING (village_id)
    WHERE z < 14 AND v.geom && b.env)
  SELECT ST_AsMVT(mvt, 'villages', 4096, 'geom') FROM mvt;
$$;
