-- Q9: fuzzy village search for a transliteration variant (FR-2). ILIKE '%...%' vs trigram GIN (I9).
-- variant: ilike
-- setup: DROP INDEX village_name_trgm
SELECT village_id, name FROM village WHERE name ILIKE '%' || :q_village_fragment || '%' LIMIT 10;
-- variant: trigram_gin
-- size: village_name_trgm
SELECT village_id, name, similarity(name, :q_village) AS sim FROM village
WHERE name % :q_village ORDER BY sim DESC LIMIT 10;
