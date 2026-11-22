-- Q7: sales in a 3-month window, with partition pruning. No index vs B-tree twin vs BRIN (I4). Index size MB.
-- variant: no_index
-- setup: DROP INDEX sale_date_brin
-- setup: SET LOCAL enable_indexscan = off
-- setup: SET LOCAL enable_indexonlyscan = off
-- setup: SET LOCAL enable_bitmapscan = off
SELECT count(*), sum(consideration_inr) FROM sale_transaction
WHERE registered_on >= DATE '2024-01-01' AND registered_on < DATE '2024-04-01';
-- variant: btree
-- setup: DROP INDEX sale_date_brin
-- setup: CREATE INDEX bench_sale_date_btree ON sale_transaction (registered_on)
-- size: bench_sale_date_btree
SELECT count(*), sum(consideration_inr) FROM sale_transaction
WHERE registered_on >= DATE '2024-01-01' AND registered_on < DATE '2024-04-01';
-- variant: brin
-- size: sale_date_brin
SELECT count(*), sum(consideration_inr) FROM sale_transaction
WHERE registered_on >= DATE '2024-01-01' AND registered_on < DATE '2024-04-01';
