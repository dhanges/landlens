-- Q2: parcels within 2 km of active projects (latest status as of today is sanctioned or under construction).
-- No index vs GiST (I1) vs GiST + partial (I6).
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
