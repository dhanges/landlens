-- Q4: one parcel's price history. No index vs composite B-tree (I3).
-- variant: no_index
-- setup: DROP INDEX sale_parcel_date_ix
SELECT registered_on, consideration_inr, area_sqm FROM sale_transaction
WHERE parcel_id = :busy_pid ORDER BY registered_on DESC;
-- variant: composite_btree
-- size: sale_parcel_date_ix
SELECT registered_on, consideration_inr, area_sqm FROM sale_transaction
WHERE parcel_id = :busy_pid ORDER BY registered_on DESC;
