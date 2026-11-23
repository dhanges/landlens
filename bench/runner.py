"""LandLens benchmark runner (spec 2.19, spec 3.3 M2).

For every variant of q1..q9: BEGIN; run its setup (drop an index, or create a B-tree twin); 2 warm-ups plus 10
timed runs of EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON); record median and p95 execution time, plan node types,
indexes used, shared buffers and pg_relation_size of every index involved; ROLLBACK, so the database is unchanged.
Q5 also reports the cost of REFRESH MATERIALIZED VIEW CONCURRENTLY. Q8 is skipped while document_chunk is empty
(it needs the M5 corpus and runs in M6). Results go to results/sf<N>.csv. Losing variants are reported as they are.

Run inside the api container: `landlens bench` (or `make bench`).
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

import psycopg

from landlens.db import connect

HERE = Path(__file__).resolve().parent
WARMUPS, RUNS = 2, 10
TIMEOUT_S, SLOW_MS, SLOW_RUNS = 300, 20_000, 3   # slow baselines: fewer runs, timeouts recorded
CASTS = {"pt": "geometry", "land_type": "land_type", "scr_type": "land_type", "scr_zones": "text[]",
         "scr_max_proj": "numeric", "scr_min_cagr": "numeric", "scr_sel_min_cagr": "numeric", "scr_last_cagr": "numeric", "scr_last_id": "bigint",
         "pid": "bigint", "busy_pid": "bigint", "vid": "integer", "q_vec": "vector", "q_text": "text",
         "q_village": "text", "q_village_fragment": "text"}
PARAM_RE = re.compile(r"(?<![:\w]):([a-z_]+)\b")
FIELDS = ["scale_factor", "query", "variant", "median_ms", "p95_ms", "runs", "plan_nodes", "indexes_used",
          "shared_hit", "shared_read", "index_size_mb", "rows", "note"]


def parse(path: Path) -> dict:
    """Split a query file into variants: {'title', 'requires', 'refresh', 'variants': [{name, setup, size, sql}]}."""
    out = {"title": "", "requires": None, "refresh": None, "variants": []}
    cur = None
    for line in path.read_text().splitlines():
        s = line.strip()
        if s.startswith("-- variant:"):
            cur = {"name": s.split(":", 1)[1].strip(), "setup": [], "size": [], "sql": []}
            out["variants"].append(cur)
        elif s.startswith("-- setup:") and cur is not None:
            cur["setup"].append(s.split(":", 1)[1].strip())
        elif s.startswith("-- size:") and cur is not None:
            cur["size"] += [x.strip() for x in s.split(":", 1)[1].split(",") if x.strip()]
        elif s.startswith("-- requires:"):
            out["requires"] = s.split(":", 1)[1].strip()
        elif s.startswith("-- refresh:"):
            out["refresh"] = s.split(":", 1)[1].strip()
        elif s.startswith("--"):
            if not out["title"] and cur is None:
                out["title"] = s[2:].strip()
        elif cur is not None:
            cur["sql"].append(line)
    for v in out["variants"]:
        v["sql"] = "\n".join(v["sql"]).strip().rstrip(";")
    return out


def bind(sql_text: str) -> str:
    sql_text = sql_text.replace("%", "%%")
    return PARAM_RE.sub(lambda m: f"%({m.group(1)})s::{CASTS[m.group(1)]}" if m.group(1) in CASTS else m.group(0), sql_text)


def walk(plan: dict, nodes: set, idx: set) -> None:
    nodes.add(plan["Node Type"])
    if plan.get("Index Name"):
        idx.add(plan["Index Name"])
    for p in plan.get("Plans", []):
        walk(p, nodes, idx)


def context(cur) -> dict:
    c = {}
    cur.execute("SELECT ST_AsHexEWKB(ST_Transform(ST_SetSRID(ST_MakePoint(79.5941, 17.9689), 4326), 32644))")
    c["pt"] = cur.fetchone()[0]
    cur.execute("SELECT parcel_id, land_type::text, village_id FROM parcel WHERE ST_Contains(geom, %s::geometry)", (c["pt"],))
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT parcel_id, land_type::text, village_id FROM parcel ORDER BY centroid <-> %s::geometry LIMIT 1", (c["pt"],))
        row = cur.fetchone()
    c["pid"], c["land_type"], c["vid"] = row
    cur.execute("SELECT parcel_id FROM sale_transaction GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1")
    c["busy_pid"] = cur.fetchone()[0]
    # screener: the most common land type and its 3 most common zones; relax min CAGR until page 50 exists
    cur.execute("SELECT land_type::text FROM mv_parcel_metrics GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    c["scr_type"] = cur.fetchone()[0]
    cur.execute("""SELECT zone_code FROM mv_parcel_metrics WHERE land_type = %s::land_type AND zone_code IS NOT NULL
                   GROUP BY 1 ORDER BY count(*) DESC LIMIT 3""", (c["scr_type"],))
    c["scr_zones"] = [r[0] for r in cur.fetchall()]
    c["scr_max_proj"] = 3000
    where = ("land_type = %(t)s::land_type AND zone_code = ANY(%(z)s) AND nearest_active_project_m <= %(p)s "
             "AND cagr_5y >= %(c)s AND gw_category <> 'over_exploited'")
    c["scr_min_cagr"] = 0.10
    while True:
        cur.execute(f"SELECT count(*) FROM mv_parcel_metrics WHERE {where}",
                    {"t": c["scr_type"], "z": c["scr_zones"], "p": c["scr_max_proj"], "c": c["scr_min_cagr"]})
        n = cur.fetchone()[0]
        if n >= 2600 or c["scr_min_cagr"] <= -0.5:
            break
        c["scr_min_cagr"] = round(c["scr_min_cagr"] - 0.02, 2)
    c["scr_matches"] = n
    # selective variant (M2 fix): min CAGR at the 99th percentile of the rows matching the other filters
    sel_where = where.replace("cagr_5y >= %(c)s", "cagr_5y IS NOT NULL")
    cur.execute(f"SELECT percentile_disc(0.99) WITHIN GROUP (ORDER BY cagr_5y) FROM mv_parcel_metrics WHERE {sel_where}",
                {"t": c["scr_type"], "z": c["scr_zones"], "p": c["scr_max_proj"]})
    c["scr_sel_min_cagr"] = cur.fetchone()[0]
    cur.execute(f"SELECT count(*) FROM mv_parcel_metrics WHERE {where}",
                {"t": c["scr_type"], "z": c["scr_zones"], "p": c["scr_max_proj"], "c": c["scr_sel_min_cagr"]})
    c["scr_sel_matches"] = cur.fetchone()[0]
    cur.execute(f"""SELECT cagr_5y, parcel_id FROM mv_parcel_metrics WHERE {where}
                    ORDER BY cagr_5y DESC, parcel_id DESC OFFSET 2449 LIMIT 1""",
                {"t": c["scr_type"], "z": c["scr_zones"], "p": c["scr_max_proj"], "c": c["scr_min_cagr"]})
    last = cur.fetchone()
    c["scr_last_cagr"], c["scr_last_id"] = (last if last else (None, None))
    c["q_village"], c["q_village_fragment"] = "Hanmakonda", "hanam"   # FR-2 transliteration example
    cur.execute("SELECT count(*) FROM document_chunk")
    c["chunks"] = cur.fetchone()[0]
    if c["chunks"]:
        # Q8 rotates through 20 (text, vector) pairs, one per timed run: texts are the eval set's answerable questions
        # (bench/rag_eval_questions.json), vectors are stored chunk embeddings sampled by a fixed hash order, so
        # Q8 needs no OpenAI call. Retrieval quality per method (recall@10 against expected pages) comes from
        # the paid eval run (bench/rag_eval.py), which embeds the questions themselves.
        cur.execute("SELECT embedding::text FROM document_chunk ORDER BY md5(document_id || '-' || chunk_no) LIMIT 20")
        vecs = [r[0] for r in cur.fetchall()]
        qf = HERE / "rag_eval_questions.json"
        texts = [q["question"] for q in json.loads(qf.read_text())["questions"] if q["answerable"]] if qf.exists() else []
        if not texts:
            cur.execute("SELECT left(content, 60) FROM document_chunk ORDER BY document_id, chunk_no LIMIT 20")
            texts = [r[0] for r in cur.fetchall()]
        c["q_rot"] = [{"q_text": texts[i % len(texts)], "q_vec": v} for i, v in enumerate(vecs)]
        c["q_vec"], c["q_text"] = c["q_rot"][0]["q_vec"], c["q_rot"][0]["q_text"]
    return c


def explain(cur, sql_text: str, params: dict, raw: bool = False) -> dict:
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql_text if raw else bind(sql_text)}", params)
    doc = cur.fetchone()[0]
    return (json.loads(doc) if isinstance(doc, str) else doc)[0]


def run_variant(conn, qid: str, v: dict, params: dict, sf: int) -> dict:
    row = {"scale_factor": sf, "query": qid, "variant": v["name"], "note": ""}
    with conn.transaction(force_rollback=True), psycopg.ClientCursor(conn) as cur:
        cur.execute(f"SET LOCAL statement_timeout = '{TIMEOUT_S}s'")
        for s in v["setup"]:
            cur.execute(s)
        if any(s.upper().startswith(("DROP INDEX", "CREATE INDEX")) for s in v["setup"]):
            cur.execute("ANALYZE")       # plans should see the changed index set
        times, last, note = [], None, []
        warmups, runs = WARMUPS, RUNS
        i = 0
        while i < warmups + runs:
            rot = params.get("q_rot") if qid == "Q8" else None
            p = {**params, **rot[i % len(rot)]} if rot else params
            try:
                last = explain(cur, v["sql"], p, v.get("raw", False))
            except psycopg.errors.QueryCanceled:
                row.update(note=f"timed out after {TIMEOUT_S} s" + (f"; {'; '.join(v['setup'])}" if v["setup"] else ""))
                return row
            if i == 0 and last["Execution Time"] > SLOW_MS:      # slow baseline: 1 warm-up + 3 timed runs
                warmups, runs = 1, SLOW_RUNS
                note.append(f"slow variant: {SLOW_RUNS} timed runs after 1 warm-up")
            if i >= warmups:
                times.append(last["Execution Time"])
            i += 1
        nodes, idx = set(), set()
        walk(last["Plan"], nodes, idx)
        size = 0.0
        for name in v["size"]:
            cur.execute("SELECT pg_relation_size(c.oid) + coalesce((SELECT sum(pg_relation_size(i.inhrelid)) "
                        "FROM pg_inherits i WHERE i.inhparent = c.oid), 0) FROM pg_class c WHERE c.relname = %s", (name,))
            r = cur.fetchone()
            size += float(r[0] or 0) if r else 0.0
        times.sort()
        row.update(median_ms=round(statistics.median(times), 3), p95_ms=round(times[min(len(times) - 1, int(0.95 * len(times)))], 3),
                   runs=len(times), plan_nodes="|".join(sorted(nodes)), indexes_used="|".join(sorted(idx)),
                   shared_hit=last["Plan"].get("Shared Hit Blocks", 0), shared_read=last["Plan"].get("Shared Read Blocks", 0),
                   index_size_mb=round(size / 1024 / 1024, 2) if v["size"] else "", rows=last["Plan"].get("Actual Rows"))
        row["note"] = "; ".join(note + v["setup"])
    return row


def recall_at_10(conn, params: dict) -> float | None:
    """HNSW recall@10 against the exact scan, averaged over the Q8 query vectors (hnsw.ef_search default 40)."""
    rot = params.get("q_rot") or [{"q_vec": params["q_vec"]}]
    q = bind("SELECT document_id, chunk_no FROM document_chunk ORDER BY embedding <=> :q_vec LIMIT 10")
    with conn.transaction(force_rollback=True), psycopg.ClientCursor(conn) as cur:
        cur.execute("SET LOCAL enable_seqscan = off")            # make the small table use the index
        hnsw = []
        for r in rot:
            cur.execute(q, {**params, **r})
            hnsw.append(set(cur.fetchall()))
        cur.execute("DROP INDEX chunk_emb_hnsw")
        exact = []
        for r in rot:
            cur.execute(q, {**params, **r})
            exact.append(set(cur.fetchall()))
    return round(statistics.mean(len(h & e) / max(len(e), 1) for h, e in zip(hnsw, exact, strict=True)), 3)


def main(argv: list[str]) -> int:
    only = set(argv)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT coalesce(max(scale_factor), 0) FROM parcel_coverage")
            sf = cur.fetchone()[0]
            params = context(cur)
        conn.commit()
        print(f"bench at SF{sf}: point parcel {params['pid']} ({params['land_type']}), busiest parcel "
              f"{params['busy_pid']}, village {params['vid']}; screener {params['scr_type']} zones {params['scr_zones']} "
              f"min_cagr {params['scr_min_cagr']} -> {params['scr_matches']} matches; selective min_cagr "
              f"{params['scr_sel_min_cagr']} -> {params['scr_sel_matches']} matches")
        rows = []
        for path in sorted((HERE / "queries").glob("q*.sql")):
            qid = path.stem.upper()
            if only and qid not in only:
                continue
            spec = parse(path)
            if spec["requires"] and not params.get("chunks"):
                print(f"{qid} skipped: {spec['requires']} is empty (run landlens ingest-pdf first; Q8 runs in M6)")
                rows.append({"scale_factor": sf, "query": qid, "variant": "-", "note": f"skipped: {spec['requires']} empty"})
                continue
            if qid == "Q8":       # the API's own statement (services/rag.py), timed as /chat runs it
                from landlens.app.services.rag import CANDIDATES, RETRIEVE, RRF_K
                params.update(any_term=False, cand=CANDIDATES, rrf=RRF_K, k=10)
                for r in params.get("q_rot", []):
                    r.update(q=r["q_text"], emb=r["q_vec"])
                spec["variants"].append({"name": "hybrid_api_statement", "setup": [], "size": [], "raw": True,
                                         "sql": RETRIEVE})
            for v in spec["variants"]:
                if qid == "Q6" and "keyset" in v["name"] and params["scr_last_id"] is None:
                    rows.append({"scale_factor": sf, "query": qid, "variant": v["name"], "note": "skipped: fewer than 50 pages"})
                    continue
                r = run_variant(conn, qid, v, params, sf)
                rows.append(r)
                if "median_ms" in r:
                    print(f"{qid} {v['name']:<28} median {r['median_ms']:>10.3f} ms  p95 {r['p95_ms']:>10.3f} ms  "
                          f"{(r['indexes_used'] or r['plan_nodes'])[:80]}")
                else:
                    print(f"{qid} {v['name']:<28} {r['note']}")
            if spec["refresh"]:
                conn.autocommit = True
                t0 = time.perf_counter()
                conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {spec['refresh']}")
                ms = (time.perf_counter() - t0) * 1000
                conn.autocommit = False
                rows.append({"scale_factor": sf, "query": qid, "variant": "refresh_concurrently", "median_ms": round(ms, 1),
                             "p95_ms": round(ms, 1), "runs": 1, "note": f"REFRESH MATERIALIZED VIEW CONCURRENTLY {spec['refresh']}"})
                print(f"{qid} refresh_concurrently        {ms:>10.1f} ms")
            if qid == "Q8":
                rec = recall_at_10(conn, params)
                rows.append({"scale_factor": sf, "query": qid, "variant": "hnsw_recall_at_10", "note": f"recall@10 = {rec}"})
    out = HERE / "results" / f"sf{sf}.csv"
    out.parent.mkdir(exist_ok=True)
    if only and out.exists():       # a subset run replaces only those queries' rows
        with out.open() as fh:
            kept = [r for r in csv.DictReader(fh) if r["query"] not in only]
        rows = sorted(kept + rows, key=lambda r: int(str(r["query"])[1:]))
    tmp = out.with_suffix(".csv.tmp")   # write then rename: replaces the file even if another user owns it
    with tmp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(out)
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
