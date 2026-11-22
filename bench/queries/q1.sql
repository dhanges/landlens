-- Q1: parcel at a clicked point (spec 2.19). Seq scan vs GiST (I1).
-- variant: seq_scan
-- setup: DROP INDEX parcel_geom_gix
SELECT parcel_id FROM parcel WHERE ST_Contains(geom, :pt);
-- variant: gist
-- size: parcel_geom_gix
SELECT parcel_id FROM parcel WHERE ST_Contains(geom, :pt);
