-- 010: indexes (spec 2.7), post-load phase (spec 2.17): built once, after the bulk load.
-- I5 (the screener's covering index) is created with mv_parcel_metrics in 011 (spec 2.6).

-- I1 spatial (GiST)
CREATE INDEX parcel_geom_gix      ON parcel        USING gist (geom);
CREATE INDEX plan_zone_geom_gix   ON plan_zone     USING gist (geom);
CREATE INDEX infra_geom_gix       ON infra_feature USING gist (geom);
CREATE INDEX project_geom_gix     ON dev_project   USING gist (geom);
CREATE INDEX village_geom_gix     ON village       USING gist (geom);
CREATE INDEX soil_geom_gix        ON soil_sample   USING gist (geom);
-- I2 KNN comparables
CREATE INDEX parcel_centroid_gix  ON parcel USING gist (centroid);
-- I3 price history per parcel
CREATE INDEX sale_parcel_date_ix  ON sale_transaction (parcel_id, registered_on DESC);
-- I4 date-range scans, compared with a B-tree twin during benchmarks
CREATE INDEX sale_date_brin       ON sale_transaction USING brin (registered_on);
-- I6 partial: active projects only
CREATE INDEX project_status_active_ix ON project_status_history (project_id, effective_from DESC)
  WHERE status IN ('sanctioned','under_construction');
-- I7 full-text
CREATE INDEX chunk_tsv_gin   ON document_chunk USING gin (tsv);
-- I8 semantic search
CREATE INDEX chunk_emb_hnsw  ON document_chunk USING hnsw (embedding vector_cosine_ops);
-- I9 fuzzy village search
CREATE INDEX village_name_trgm ON village USING gin (name gin_trgm_ops);
-- supporting
CREATE INDEX ledger_user_ix  ON credit_ledger (user_id, created_at DESC);
CREATE INDEX impact_project_ix ON parcel_project_impact (project_id, distance_m);

ANALYZE;
