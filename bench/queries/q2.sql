-- Q2: parcels within 2 km of active projects (latest status as of today is sanctioned or under construction).
-- No index vs GiST (I1) vs GiST + partial (I6); then two M2-fix variants:
--   gist_subdivided: project geometries cut into small pieces (ST_Segmentize 250 m + ST_Subdivide 16 vertices)
--     in a helper table with its own GiST, so a ring road's bounding box no longer spans the core. The helper
--     table is built in the variant's setup (untimed, rolled back with the variant).
--   impact_lookup: the precomputed parcel_project_impact table (distance_m within 10 km) read through
--     impact_project_ix. Its distance is parcel centroid to project (load.py derive), not parcel geometry to
--     project, so its count can be slightly lower than the ST_DWithin(p.geom, ...) variants.
-- variant: no_index
-- setup: DROP INDEX parcel_geom_gix
-- setup: DROP INDEX project_geom_gix
-- setup: DROP INDEX project_status_active_ix
WITH active AS (
  SELECT j.project_id, j.geom FROM dev_project j
  WHERE EXISTS (SELECT 1 FROM project_status_history h
                WHERE h.project_id = j.project_id AND h.status IN ('sanctioned', 'under_construction')
                  AND h.effective_from <= landlens_as_of()
                  AND NOT EXISTS (SELECT 1 FROM project_status_history l
                                  WHERE l.project_id = j.project_id AND l.effective_from > h.effective_from
                                    AND l.effective_from <= landlens_as_of())))
SELECT count(DISTINCT p.parcel_id) FROM parcel p JOIN active a ON ST_DWithin(p.geom, a.geom, 2000);
-- variant: gist
-- setup: DROP INDEX project_status_active_ix
-- size: parcel_geom_gix
WITH active AS (
  SELECT j.project_id, j.geom FROM dev_project j
  WHERE EXISTS (SELECT 1 FROM project_status_history h
                WHERE h.project_id = j.project_id AND h.status IN ('sanctioned', 'under_construction')
                  AND h.effective_from <= landlens_as_of()
                  AND NOT EXISTS (SELECT 1 FROM project_status_history l
                                  WHERE l.project_id = j.project_id AND l.effective_from > h.effective_from
                                    AND l.effective_from <= landlens_as_of())))
SELECT count(DISTINCT p.parcel_id) FROM parcel p JOIN active a ON ST_DWithin(p.geom, a.geom, 2000);
-- variant: gist_partial
-- size: parcel_geom_gix, project_status_active_ix
WITH active AS (
  SELECT j.project_id, j.geom FROM dev_project j
  WHERE EXISTS (SELECT 1 FROM project_status_history h
                WHERE h.project_id = j.project_id AND h.status IN ('sanctioned', 'under_construction')
                  AND h.effective_from <= landlens_as_of()
                  AND NOT EXISTS (SELECT 1 FROM project_status_history l
                                  WHERE l.project_id = j.project_id AND l.effective_from > h.effective_from
                                    AND l.effective_from <= landlens_as_of())))
SELECT count(DISTINCT p.parcel_id) FROM parcel p JOIN active a ON ST_DWithin(p.geom, a.geom, 2000);
-- variant: gist_subdivided
-- setup: CREATE TABLE bench_project_piece AS SELECT project_id, ST_Subdivide(ST_Segmentize(geom, 250), 16) AS geom FROM dev_project
-- setup: CREATE INDEX bench_project_piece_gix ON bench_project_piece USING gist (geom)
-- size: parcel_geom_gix, project_status_active_ix, bench_project_piece_gix
WITH active AS (
  SELECT j.project_id, j.geom FROM dev_project j
  WHERE EXISTS (SELECT 1 FROM project_status_history h
                WHERE h.project_id = j.project_id AND h.status IN ('sanctioned', 'under_construction')
                  AND h.effective_from <= landlens_as_of()
                  AND NOT EXISTS (SELECT 1 FROM project_status_history l
                                  WHERE l.project_id = j.project_id AND l.effective_from > h.effective_from
                                    AND l.effective_from <= landlens_as_of())))
SELECT count(DISTINCT p.parcel_id)
FROM active a JOIN bench_project_piece s USING (project_id) JOIN parcel p ON ST_DWithin(p.geom, s.geom, 2000);
-- variant: impact_lookup
-- size: impact_project_ix, project_status_active_ix
WITH active AS (
  SELECT j.project_id, j.geom FROM dev_project j
  WHERE EXISTS (SELECT 1 FROM project_status_history h
                WHERE h.project_id = j.project_id AND h.status IN ('sanctioned', 'under_construction')
                  AND h.effective_from <= landlens_as_of()
                  AND NOT EXISTS (SELECT 1 FROM project_status_history l
                                  WHERE l.project_id = j.project_id AND l.effective_from > h.effective_from
                                    AND l.effective_from <= landlens_as_of())))
SELECT count(DISTINCT i.parcel_id)
FROM active a JOIN parcel_project_impact i USING (project_id) WHERE i.distance_m <= 2000;
