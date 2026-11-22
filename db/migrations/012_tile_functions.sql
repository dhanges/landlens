-- 012: vector tile functions served by Martin (spec 2.8, 2.2, ADR-007), post-load phase.
-- Signature (z, x, y) -> bytea so Martin auto-discovers them as function sources named after the function.
-- tiles_parcels is exactly spec 2.8. Others simplify per zoom (spec 2.18): tolerance ~ half a pixel in metres.
-- tiles_coverage serves parcel_coverage (DEC-004). Functions run with the caller's rights; landlens_tiles has
-- SELECT on the tables (013) and views (011) they read.

CREATE FUNCTION tiles_parcels(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env),
  mvt AS (
    SELECT m.parcel_id, m.land_type, m.price_sqm, m.cagr_5y,
           ST_AsMVTGeom(ST_Transform(p.geom, 3857), b.env3857) AS geom
    FROM b, parcel p JOIN mv_parcel_metrics m USING (parcel_id)
    WHERE z >= 14 AND p.geom && b.env)
  SELECT ST_AsMVT(mvt, 'parcels', 4096, 'geom') FROM mvt;
$$;

-- Below zoom 14, village polygons coloured by median price (spec 2.8): the most recent year's median of the
-- village's best-sampled land type.
CREATE FUNCTION tiles_villages(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env,
                    156543.0 / (2 ^ z) / 2 AS tol),
  mvt AS (
    SELECT v.village_id, v.name, v.mandal_id, v.boundary_source::text AS boundary_source,
           (SELECT i.median_price_sqm FROM mv_village_price_index i
             WHERE i.village_id = v.village_id ORDER BY i.yr DESC, i.n_sales DESC LIMIT 1) AS median_price_sqm,
           ST_AsMVTGeom(ST_Transform(ST_SimplifyPreserveTopology(v.geom, b.tol), 3857), b.env3857) AS geom
    FROM b, village v
    WHERE z < 14 AND v.geom && b.env)
  SELECT ST_AsMVT(mvt, 'villages', 4096, 'geom') FROM mvt;
$$;

CREATE FUNCTION tiles_zones(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env,
                    156543.0 / (2 ^ z) / 2 AS tol),
  mvt AS (
    SELECT pz.zone_id, pz.zone_code, pz.source::text AS source,
           ST_AsMVTGeom(ST_Transform(ST_SimplifyPreserveTopology(pz.geom, b.tol), 3857), b.env3857) AS geom
    FROM b, plan_zone pz
    WHERE pz.geom && b.env)
  SELECT ST_AsMVT(mvt, 'zones', 4096, 'geom') FROM mvt;
$$;

CREATE FUNCTION tiles_projects(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env),
  mvt AS (
    SELECT j.project_id, j.name, j.project_type::text AS project_type, j.source::text AS source,
           (SELECT h.status::text FROM project_status_history h
             WHERE h.project_id = j.project_id AND h.effective_from <= landlens_as_of()
             ORDER BY h.effective_from DESC LIMIT 1) AS status,
           ST_AsMVTGeom(ST_Transform(j.geom, 3857), b.env3857) AS geom
    FROM b, dev_project j
    WHERE j.geom && b.env)
  SELECT ST_AsMVT(mvt, 'projects', 4096, 'geom') FROM mvt;
$$;

-- roads and water bodies are one source, filtered by feature_type in the map style; minor roads from zoom 13
CREATE FUNCTION tiles_infra(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env,
                    156543.0 / (2 ^ z) / 2 AS tol),
  mvt AS (
    SELECT f.feature_id, f.feature_type::text AS feature_type, f.name, f.source::text AS source,
           ST_AsMVTGeom(ST_Transform(ST_SimplifyPreserveTopology(f.geom, b.tol), 3857), b.env3857) AS geom
    FROM b, infra_feature f
    WHERE f.geom && b.env AND (z >= 13 OR f.feature_type <> 'minor_road'))
  SELECT ST_AsMVT(mvt, 'infra', 4096, 'geom') FROM mvt;
$$;

CREATE FUNCTION tiles_coverage(z integer, x integer, y integer)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
  WITH b AS (SELECT ST_TileEnvelope(z, x, y) AS env3857,
                    ST_Transform(ST_TileEnvelope(z, x, y), 32644) AS env,
                    156543.0 / (2 ^ z) / 2 AS tol),
  mvt AS (
    SELECT c.scale_factor, c.core_radius_m, c.corridor_halfwidth_m,
           ST_AsMVTGeom(ST_Transform(ST_SimplifyPreserveTopology(c.geom, b.tol), 3857), b.env3857) AS geom
    FROM b, parcel_coverage c
    WHERE c.geom && b.env)
  SELECT ST_AsMVT(mvt, 'coverage', 4096, 'geom') FROM mvt;
$$;

GRANT EXECUTE ON FUNCTION tiles_parcels(integer, integer, integer), tiles_villages(integer, integer, integer),
  tiles_zones(integer, integer, integer), tiles_projects(integer, integer, integer),
  tiles_infra(integer, integer, integer), tiles_coverage(integer, integer, integer) TO landlens_tiles;
REVOKE EXECUTE ON FUNCTION tiles_parcels(integer, integer, integer), tiles_villages(integer, integer, integer),
  tiles_zones(integer, integer, integer), tiles_projects(integer, integer, integer),
  tiles_infra(integer, integer, integer), tiles_coverage(integer, integer, integer) FROM PUBLIC;
