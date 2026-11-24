"""EXPLAIN (ANALYZE, BUFFERS) text for the benchmark results that need explaining (report pack).

Uses the runner's own parameter context, variant parsing, setup statements and binding, inside rolled-back
transactions exactly like `make bench`, so the plans are the plans the CSVs measured.
Usage (bench service): python /app/bench/explain_notes.py [out_dir]   (LANDLENS_DB_NAME selects SF5)
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import psycopg

from landlens.db import connect

HERE = Path(__file__).resolve().parent
R = runpy.run_path(str(HERE / "runner.py"), run_name="explain_notes")

PICK = {
    "Q2": ["gist", "gist_subdivided", "impact_lookup"],
    "Q3": ["order_by_st_distance", "knn"],
    "Q6": ["mv_no_covering_page1", "mv_covering_page1", "mv_covering_page50_offset", "mv_covering_page50_keyset",
           "mv_covering_selective_page1"],
    "Q7": ["no_index", "btree", "brin"],
    "Q8": ["vector_exact", "vector_hnsw", "hybrid_rrf"],
    "Q9": ["ilike", "trigram_gin"],
}


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT coalesce(max(scale_factor), 0) FROM parcel_coverage")
            sf = cur.fetchone()[0]
            params = R["context"](cur)
        conn.commit()
        for qid, names in PICK.items():
            spec = R["parse"](HERE / "queries" / f"{qid.lower()}.sql")
            if spec["requires"] and not params.get("chunks"):
                continue
            text = [f"-- {qid} at SF{sf}: EXPLAIN (ANALYZE, BUFFERS) per variant (setup applied, then rolled back)\n"]
            for v in spec["variants"]:
                if v["name"] not in names:
                    continue
                with conn.transaction(force_rollback=True), psycopg.ClientCursor(conn) as cur:
                    cur.execute("SET LOCAL statement_timeout = '300s'")
                    for s in v["setup"]:
                        cur.execute(s)
                    if any(s.upper().startswith(("DROP INDEX", "CREATE INDEX")) for s in v["setup"]):
                        cur.execute("ANALYZE")
                    p = {**params, **params["q_rot"][0]} if qid == "Q8" and params.get("q_rot") else params
                    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {R['bind'](v['sql'])}", p)
                    plan = "\n".join(r[0] for r in cur.fetchall())
                text.append(f"\n== {qid} {v['name']}" + (f"   [setup: {'; '.join(v['setup'])}]" if v["setup"] else "") + f"\n{plan}\n")
            (out / f"explain_{qid.lower()}_sf{sf}.txt").write_text("".join(text))
            print(f"wrote explain_{qid.lower()}_sf{sf}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "results" / "explain")))
