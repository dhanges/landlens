"""Document Q&A pipeline for POST /chat (spec 2.13, 2.14; FR-8; ADR-012).

1. Embed the question (text-embedding-3-small). No key, timeout (10 s) or error -> degraded mode.
2. One SQL statement: keyword candidates (full text, top 40) and vector candidates (HNSW cosine, top 40),
   fused by Reciprocal Rank Fusion (k = 60), top 6, plus the keyword hit count and the best cosine distance
   for the not-found rule. Degraded mode runs the same statement without a vector, keyword-only, with the
   question's terms OR-ed (websearch AND-semantics would find little for natural questions).
3. Not-found rule: no keyword hits and best cosine distance > CHAT_MAX_DISTANCE (0.6) -> found: false, no LLM call.
4. Generation from numbered excerpts only, temperature 0; every [n] must refer to a given excerpt. Unknown [n]
   are dropped; if none remain, the excerpts are returned without an answer (spec 2.14). An LLM failure
   returns the excerpts with degraded: true.
"""

from __future__ import annotations

import re

from psycopg_pool import AsyncConnectionPool

from landlens.rag.llm import LLMUnavailable

TOP_K = 6
CANDIDATES = 40
RRF_K = 60
NOT_FOUND = "not found in the documents"
SNIPPET_CHARS = 320

RETRIEVE = """
WITH kw AS (
  SELECT document_id, chunk_no, row_number() OVER (ORDER BY rank DESC, document_id, chunk_no) AS r
  FROM (SELECT c.document_id, c.chunk_no, ts_rank_cd(c.tsv, q) AS rank
        FROM document_chunk c,
             (SELECT CASE WHEN %(any_term)s
                          THEN replace(plainto_tsquery('english', %(q)s)::text, ' & ', ' | ')::tsquery
                          ELSE websearch_to_tsquery('english', %(q)s) END AS q) tq
        WHERE numnode(q) > 0 AND c.tsv @@ q
        ORDER BY rank DESC LIMIT %(cand)s) s),
vec AS (
  SELECT document_id, chunk_no, d, row_number() OVER (ORDER BY d, document_id, chunk_no) AS r
  FROM (SELECT c.document_id, c.chunk_no, c.embedding <=> %(emb)s::vector AS d
        FROM document_chunk c
        WHERE %(emb)s::vector IS NOT NULL
        ORDER BY c.embedding <=> %(emb)s::vector LIMIT %(cand)s) s),
fused AS (
  SELECT document_id, chunk_no, kw.r AS kw_rank, vec.r AS vec_rank, vec.d AS distance,
         coalesce(1.0 / (%(rrf)s + kw.r), 0) + coalesce(1.0 / (%(rrf)s + vec.r), 0) AS score
  FROM kw FULL JOIN vec USING (document_id, chunk_no))
SELECT f.document_id, f.chunk_no, f.kw_rank, f.vec_rank, f.distance, f.score,
       c.page_start, c.page_end, c.content, d.title,
       (SELECT count(*) FROM kw) AS kw_hits, (SELECT min(vec.d) FROM vec) AS best_distance
FROM fused f
JOIN document_chunk c USING (document_id, chunk_no)
JOIN document d USING (document_id)
ORDER BY f.score DESC, f.document_id, f.chunk_no
LIMIT %(k)s"""

SYSTEM = (
    "You answer questions about Telangana land, planning and development law using ONLY the numbered excerpts "
    "the user gives you. Cite every statement with the excerpt number in square brackets, like [2]. Use only "
    "excerpt numbers that exist. Do not use outside knowledge. If the excerpts do not answer the question, reply "
    f"with exactly: {NOT_FOUND}. Answer in plain sentences, at most 150 words."
)


def vector_literal(v: list[float] | None) -> str | None:
    return None if v is None else "[" + ",".join(f"{x:.7f}" for x in v) + "]"


async def retrieve(pool: AsyncConnectionPool, question: str, emb: list[float] | None, k: int = TOP_K) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(RETRIEVE, {"q": question, "emb": vector_literal(emb), "any_term": emb is None,
                                            "cand": CANDIDATES, "rrf": RRF_K, "k": k})
        return await cur.fetchall()


def snippet(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= SNIPPET_CHARS else t[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"


def citation(n: int, r: dict) -> dict:
    return {"n": n, "document_id": r["document_id"], "title": r["title"], "page_start": r["page_start"],
            "page_end": r["page_end"], "snippet": snippet(r["content"])}


def build_messages(question: str, rows: list[dict], context: str | None) -> list[dict]:
    parts = [f"Question: {question}"]
    if context:
        parts.append(f"Context (not a source, do not cite): {context}")
    parts.append("Excerpts:")
    for n, r in enumerate(rows, start=1):
        pages = f"page {r['page_start']}" if r["page_start"] == r["page_end"] else f"pages {r['page_start']}-{r['page_end']}"
        parts.append(f"[{n}] {r['title']}, {pages}:\n{r['content']}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]


CITE = re.compile(r"\[(\d{1,2})\]")


def check_citations(answer: str, n_rows: int) -> tuple[str, list[int]]:
    """Drop [n] that point to no excerpt; return the cleaned answer and the valid numbers in order of use."""
    used: list[int] = []

    def keep(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= n_rows:
            if n not in used:
                used.append(n)
            return m.group(0)
        return ""

    cleaned = re.sub(r"\s+([.,;:])", r"\1", CITE.sub(keep, answer)).strip()
    return cleaned, used


async def answer(pool: AsyncConnectionPool, llm, question: str, max_distance: float,
                 context: str | None = None) -> dict:
    degraded, reason = False, None
    try:
        emb = (await llm.embed([question]))[0]
    except LLMUnavailable as e:
        emb, degraded, reason = None, True, str(e)
    rows = await retrieve(pool, question, emb)
    base = {"found": False, "degraded": degraded, "answer": None, "citations": []}

    if degraded:
        if not rows:
            return {**base, "answer": NOT_FOUND,
                    "note": "Document search is in keyword-only mode and found no matching passage."}
        return {**base, "found": True, "citations": [citation(n, r) for n, r in enumerate(rows, 1)],
                "note": "Answers are unavailable right now"
                        + (" (no OpenAI key configured)" if reason == "no_key" else "")
                        + ": these are the passages that best match your words."}

    kw_hits = rows[0]["kw_hits"] if rows else 0
    best = rows[0]["best_distance"] if rows else None
    if not rows or (kw_hits == 0 and (best is None or best > max_distance)):
        return {**base, "answer": NOT_FOUND}

    try:
        text = await llm.chat(build_messages(question, rows, context))
    except LLMUnavailable:
        return {**base, "found": True, "degraded": True, "citations": [citation(n, r) for n, r in enumerate(rows, 1)],
                "note": "The answer service did not respond: these are the most relevant passages."}

    if NOT_FOUND in text.lower():
        return {**base, "answer": NOT_FOUND}
    cleaned, used = check_citations(text, len(rows))
    if not used:
        return {**base, "found": True, "citations": [citation(n, r) for n, r in enumerate(rows, 1)],
                "note": "The answer could not be tied to a passage, so only the passages are shown."}
    return {**base, "found": True, "answer": cleaned, "citations": [citation(n, rows[n - 1]) for n in used]}
