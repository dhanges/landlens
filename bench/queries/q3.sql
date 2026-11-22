-- Q3: 10 nearest comparable sales (spec 2.8, with landlens_as_of() for current_date per DEC-004).
-- ORDER BY ST_Distance vs KNN <-> (I2).
-- variant: order_by_st_distance
SELECT p.parcel_id, t.registered_on, t.consideration_inr / t.area_sqm AS price_sqm,
       ST_Distance(p.centroid, :pt) AS dist_m
FROM parcel p
JOIN LATERAL (
  SELECT * FROM sale_transaction t
  WHERE t.parcel_id = p.parcel_id AND t.registered_on >= landlens_as_of() - interval '36 months'
  ORDER BY t.registered_on DESC LIMIT 1) t ON true
WHERE p.land_type = :land_type AND p.parcel_id <> :pid AND ST_DWithin(p.centroid, :pt, 5000)
ORDER BY ST_Distance(p.centroid, :pt)
LIMIT 10;
-- variant: knn
-- size: parcel_centroid_gix
SELECT p.parcel_id, t.registered_on, t.consideration_inr / t.area_sqm AS price_sqm,
       ST_Distance(p.centroid, :pt) AS dist_m
FROM parcel p
JOIN LATERAL (
  SELECT * FROM sale_transaction t
  WHERE t.parcel_id = p.parcel_id AND t.registered_on >= landlens_as_of() - interval '36 months'
  ORDER BY t.registered_on DESC LIMIT 1) t ON true
WHERE p.land_type = :land_type AND p.parcel_id <> :pid AND ST_DWithin(p.centroid, :pt, 5000)
ORDER BY p.centroid <-> :pt
LIMIT 10;
