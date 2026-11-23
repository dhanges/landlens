-- Q8: document retrieval (spec 2.8, ADR-012). Exact scan vs HNSW; keyword vs vector vs hybrid; latency and recall@10.
-- Needs the M5 corpus: the runner skips Q8 while document_chunk is empty (spec 3.3 M2 done-when).
-- requires: document_chunk
-- variant: keyword_gin
-- size: chunk_tsv_gin
SELECT document_id, chunk_no FROM document_chunk, websearch_to_tsquery('english', :q_text) q
WHERE tsv @@ q ORDER BY ts_rank_cd(tsv, q) DESC LIMIT 10;
-- variant: vector_exact
-- setup: DROP INDEX chunk_emb_hnsw
SELECT document_id, chunk_no FROM document_chunk ORDER BY embedding <=> :q_vec LIMIT 10;
-- variant: vector_hnsw
-- setup: SET LOCAL enable_seqscan = off
-- size: chunk_emb_hnsw
SELECT document_id, chunk_no FROM document_chunk ORDER BY embedding <=> :q_vec LIMIT 10;
-- variant: hybrid_rrf
WITH kw AS (
  SELECT document_id, chunk_no, row_number() OVER (ORDER BY rank DESC) AS r
  FROM (SELECT document_id, chunk_no, ts_rank_cd(tsv, q) AS rank
        FROM document_chunk, websearch_to_tsquery('english', :q_text) q
        WHERE tsv @@ q ORDER BY rank DESC LIMIT 40) s),
vec AS (
  SELECT document_id, chunk_no, row_number() OVER (ORDER BY d) AS r
  FROM (SELECT document_id, chunk_no, embedding <=> :q_vec AS d
        FROM document_chunk ORDER BY embedding <=> :q_vec LIMIT 40) s)
SELECT c.document_id, c.chunk_no, coalesce(1.0/(60 + kw.r), 0) + coalesce(1.0/(60 + vec.r), 0) AS score
FROM kw FULL JOIN vec USING (document_id, chunk_no) JOIN document_chunk c USING (document_id, chunk_no)
ORDER BY score DESC LIMIT 10;
