"""25-question RAG eval (spec 2.13): citation correctness, refusal accuracy, and retrieval recall@10 per method.

Run by the owner (paid; DEC-003 OQ-31):   make eval                 (all 25)
                                           make eval EVAL_ARGS="--dry-run"   (free: checks coverage, no API call)
                                           make eval EVAL_ARGS="--ids A03,U02"

For each question: one embedding (text-embedding-3-small), then the exact /chat pipeline (services/rag.py: the
hybrid statement, the not-found rule, generation with LLM_MODEL, the citation check). Scoring:
- answerable: correct if found and at least one citation's document and page range overlap the expected pages;
- unanswerable: correct if found is false (no answer);
- answer_correct: a correct citation AND the answer passes must_include / must_not_include / must_not_start_with
  (catches a right page with a wrong reading, e.g. "Yes" where the FAQ says No);
- retrieval recall@10 per method (keyword-only websearch, vector-only HNSW, hybrid RRF): an expected page is
  covered by one of the top 10 chunks (Q8 quality, spec 2.19).
Answers are printed and saved so a human can check them against key_facts. Target: >= 80% correct citations
and every unanswerable question refused (spec 3.3 M5).
Writes bench/results/rag_eval.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from landlens.app.services import rag
from landlens.db import conninfo
from landlens.rag.llm import EMBED_USD_PER_MTOK, LLMUnavailable, OpenAIAsync, est_tokens, llm_model

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE / "rag_eval_questions.json"
OUT = HERE / "results" / "rag_eval.json"
MAX_DISTANCE = float(os.environ.get("CHAT_MAX_DISTANCE") or 0.6)

KEYWORD = """SELECT c.document_id, c.page_start, c.page_end FROM document_chunk c, websearch_to_tsquery('english', %(q)s) q
             WHERE c.tsv @@ q ORDER BY ts_rank_cd(c.tsv, q) DESC LIMIT 10"""
VECTOR = """SELECT document_id, page_start, page_end FROM document_chunk ORDER BY embedding <=> %(emb)s::vector LIMIT 10"""


class Cached:
    """Hands the pipeline the question's precomputed embedding, so each question is embedded once."""

    def __init__(self, llm, vec):
        self.llm, self.vec = llm, vec

    async def embed(self, texts):
        return [self.vec]

    async def chat(self, messages):
        self.prompt_tokens = sum(est_tokens(m["content"]) for m in messages)
        return await self.llm.chat(messages)


def facts_ok(answer: str | None, q: dict) -> tuple[bool, list[str]]:
    """Required phrases (every group, any alternative) present; forbidden phrases and openings absent."""
    text = " ".join((answer or "").lower().split())
    problems = [f"missing one of {g}" for g in q.get("must_include", []) if not any(a.lower() in text for a in g)]
    problems += [f"contains {x!r}" for x in q.get("must_not_include", []) if x.lower() in text]
    problems += [f"starts with {x!r}" for x in q.get("must_not_start_with", []) if text.startswith(x.lower())]
    return not problems, problems


def overlaps(doc_id: int, ps: int, pe: int, expected: list[dict], ids: dict[str, int]) -> bool:
    return any(ids.get(e["file"]) == doc_id and any(ps <= p <= pe for p in e["pages"]) for e in expected)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", help="comma-separated question ids")
    a = ap.parse_args()
    qs = json.loads(QUESTIONS.read_text())["questions"]
    if a.ids:
        want = set(a.ids.split(","))
        qs = [q for q in qs if q["id"] in want]

    pool = AsyncConnectionPool(conninfo(), min_size=1, max_size=2, kwargs={"row_factory": dict_row}, open=False)
    await pool.open()
    async with pool.connection() as conn:
        docs = await (await conn.execute("SELECT document_id, file_path, title FROM document")).fetchall()
        ids = {Path(d["file_path"]).name: d["document_id"] for d in docs}
        missing = []
        for q in qs:
            for e in q["expected"]:
                if e["file"] not in ids:
                    missing.append(f"{q['id']}: {e['file']} not ingested")
                    continue
                for p in e["pages"]:
                    n = (await (await conn.execute(
                        "SELECT count(*) AS n FROM document_chunk WHERE document_id = %s AND %s BETWEEN page_start AND page_end",
                        (ids[e["file"]], p))).fetchone())["n"]
                    if not n:
                        missing.append(f"{q['id']}: no chunk covers {e['file']} page {p}")
    print(f"{len(qs)} questions, {len(docs)} documents ingested; generation model {llm_model()}")
    if missing:
        print("coverage problems:\n  " + "\n  ".join(missing))
    print(f"cost estimate: {len(qs)} question embeddings (~{len(qs) * 25} tokens, ~${len(qs) * 25 / 1e6 * EMBED_USD_PER_MTOK:.5f}) "
          f"+ up to {len(qs)} {llm_model()} calls of ~2,700 input + ~200 output tokens each "
          f"(~{len(qs) * 2700:,} input tokens; the not-found rule skips some). With gpt-4o-mini list prices "
          f"($0.15 / $0.60 per 1M) that is about ${len(qs) * (2700 * 0.15 + 200 * 0.6) / 1e6:.3f}.")
    if a.dry_run:
        await pool.close()
        return 1 if missing else 0
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set (put it in .env): nothing was sent.", file=sys.stderr)
        await pool.close()
        return 2
    if not docs:
        print("no documents ingested: run `make ingest` first", file=sys.stderr)
        await pool.close()
        return 2

    llm = OpenAIAsync()
    results = []
    try:
        for q in qs:
            t0 = time.perf_counter()
            try:
                vec = (await llm.embed([q["question"]]))[0]
            except LLMUnavailable as e:
                print(f"{q['id']}: embedding failed ({e}); stopping", file=sys.stderr)
                return 1
            cached = Cached(llm, vec)
            res = await rag.answer(pool, cached, q["question"], MAX_DISTANCE)
            secs = time.perf_counter() - t0
            emb = rag.vector_literal(vec)
            async with pool.connection() as conn:
                kw = await (await conn.execute(KEYWORD, {"q": q["question"]})).fetchall()
                vv = await (await conn.execute(VECTOR, {"emb": emb})).fetchall()
            hy = await rag.retrieve(pool, q["question"], vec, k=10)
            r = {"id": q["id"], "answerable": q["answerable"], "question": q["question"], "found": res["found"],
                 "degraded": res["degraded"], "answer": res["answer"], "note": res.get("note"),
                 "citations": [{k: c[k] for k in ("n", "title", "page_start", "page_end")} for c in res["citations"]],
                 "seconds": round(secs, 2), "prompt_tokens_est": getattr(cached, "prompt_tokens", 0),
                 "best_distance": hy[0]["best_distance"] if hy else None, "keyword_hits": hy[0]["kw_hits"] if hy else 0,
                 "key_facts": q["key_facts"]}
            r["retrieved"] = [(x["document_id"], x["chunk_no"], x["page_start"], x["page_end"]) for x in hy[:6]]
            if q["answerable"]:
                hits = [overlaps(c["document_id"], c["page_start"], c["page_end"], q["expected"], ids) for c in res["citations"]]
                r["correct"] = bool(res["found"] and any(hits))
                r["all_citations_correct"] = bool(hits) and all(hits)
                r["facts_ok"], r["fact_problems"] = facts_ok(res["answer"], q)
                r["answer_correct"] = r["correct"] and r["facts_ok"]
                for name, rows in (("keyword", kw), ("vector", vv), ("hybrid", hy)):
                    r[f"recall10_{name}"] = any(overlaps(x["document_id"], x["page_start"], x["page_end"], q["expected"], ids)
                                                for x in rows)
            else:
                r["correct"] = not res["found"]
            results.append(r)
            mark = "OK  " if r["correct"] and r.get("facts_ok", True) else "MISS"
            print(f"{mark} {q['id']} found={res['found']} cites={[(c['title'][:28], c['page_start']) for c in res['citations']]}"
                  f" d={r['best_distance'] if r['best_distance'] is None else round(r['best_distance'], 3)} kw={r['keyword_hits']}")
            print(f"     answer: {(res['answer'] or res.get('note') or '')[:300]}")
            print(f"     key facts: {q['key_facts']}")
            if r.get("fact_problems"):
                print(f"     fact check: {'; '.join(r['fact_problems'])}")
    finally:
        await llm.aclose()
        await pool.close()

    ans = [r for r in results if r["answerable"]]
    una = [r for r in results if not r["answerable"]]
    pct = lambda xs, k: round(100 * sum(bool(x.get(k)) for x in xs) / len(xs), 1) if xs else None  # noqa: E731
    summary = {
        "questions": len(results), "model": llm_model(), "max_distance": MAX_DISTANCE,
        "citation_correct_pct": pct(ans, "correct"), "all_citations_correct_pct": pct(ans, "all_citations_correct"),
        "answer_correct_pct": pct(ans, "answer_correct"),
        "refusal_accuracy_pct": pct(una, "correct"),
        "recall_at_10_pct": {m: pct(ans, f"recall10_{m}") for m in ("keyword", "vector", "hybrid")},
        "target_met": (pct(ans, "correct") or 0) >= 80 and all(r["correct"] for r in una),
        "mean_seconds": round(sum(r["seconds"] for r in results) / len(results), 2),
    }
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str) + "\n")
    tmp.replace(OUT)
    print(json.dumps(summary, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
