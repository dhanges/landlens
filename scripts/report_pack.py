"""Build report/pack/report_material.md from real outputs (M8 report pack). Never calls OpenAI.

Reads: the live SF1 (landlens_owner) and SF5 (landlens_sf5) catalogs via `docker compose exec db psql`
(row counts, keys, FK delete rules, indexes and sizes, generated columns, materialized views, documents),
bench/results/*, report/pack/explain/*, SECURITY.md, report/er-diagram.mmd, bench/rag_eval*.{json,py}.
Every number in the output names the file (or query) it came from. Usage: python3 scripts/report_pack.py
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "report" / "pack"
RES = ROOT / "bench" / "results"
DBS = {"SF1": "landlens_owner", "SF5": "landlens_sf5"}


def psql(db: str, sql: str):
    out = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "landlens_owner", "-d", db, "-At",
                          "-c", sql], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    return json.loads(out) if out else None


TABLES_SQL = """SELECT json_agg(relname ORDER BY relname) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r','p') AND NOT c.relispartition AND relname NOT LIKE 'stg\\_%'"""
INDEX_SQL = """SELECT json_agg(x ORDER BY tbl, name) FROM (
  SELECT ic.relname AS name, c.relname AS tbl, am.amname AS type, pg_get_indexdef(i.indexrelid) AS def,
         coalesce((SELECT sum(pg_relation_size(relid)) FROM pg_partition_tree(i.indexrelid)), pg_relation_size(i.indexrelid)) AS bytes
  FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid JOIN pg_class c ON c.oid = i.indrelid
  JOIN pg_am am ON am.oid = ic.relam JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND NOT ic.relispartition AND c.relname NOT LIKE 'stg\\_%') x"""
CONS_SQL = """SELECT json_agg(x ORDER BY tbl, contype, name) FROM (
  SELECT k.conrelid::regclass::text AS tbl, k.conname AS name, k.contype::text AS contype,
         pg_get_constraintdef(k.oid) AS def, k.confdeltype::text AS ondelete
  FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND NOT c.relispartition AND k.contype IN ('p','f','u') AND c.relname NOT LIKE 'stg\\_%') x"""
GEN_SQL = """SELECT json_agg(json_build_object('tbl', c.relname, 'col', a.attname, 'expr', pg_get_expr(d.adbin, d.adrelid)))
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND a.attgenerated = 's' AND NOT c.relispartition"""
MV_SQL = """SELECT json_agg(json_build_object('name', matviewname, 'rows', (xpath('/row/c/text()',
  query_to_xml(format('SELECT count(*) AS c FROM %I', matviewname), false, true, '')))[1]::text::bigint,
  'bytes', pg_total_relation_size(matviewname::regclass)) ORDER BY matviewname) FROM pg_matviews WHERE schemaname = 'public'"""
DOCS_SQL = """SELECT json_agg(json_build_object('id', d.document_id, 'title', d.title, 'pages', d.page_count,
  'chunks', (SELECT count(*) FROM document_chunk c WHERE c.document_id = d.document_id),
  'tokens_est', (SELECT sum(ceil(length(content) / 4.0)) FROM document_chunk c WHERE c.document_id = d.document_id))
  ORDER BY d.document_id) FROM document d"""
GROUPS = {
    "Geography and land": ["district", "mandal", "village", "parcel", "parcel_coverage", "plan_zone", "zone_type",
                           "parcel_zone", "master_plan"],
    "Infrastructure, projects, environment": ["infra_feature", "dev_project", "project_status_history",
                                              "parcel_project_impact", "soil_sample", "gw_assessment"],
    "Prices": ["sale_transaction", "guideline_rate"],
    "Documents": ["document", "document_chunk"],
    "Users and credits": ["app_user", "credit_ledger", "report_unlock", "watchlist"],
}
INDEX_QUERY = {  # index -> query it serves (spec 2.7 numbering, bench query ids)
    "parcel_geom_gix": "I1 Q1 point-in-parcel (/parcels/at), Q2 parcels near a project, tiles",
    "plan_zone_geom_gix": "I1 zone overlap (parcel_zone build), zone tiles",
    "infra_geom_gix": "I1 nearest highway/water (mv_parcel_metrics), infra tiles",
    "project_geom_gix": "I1 Q2 (gist variants), project tiles",
    "village_geom_gix": "I1 /parcels/at outside_coverage check, village tiles",
    "soil_geom_gix": "I1 nearest soil samples (report)",
    "parcel_centroid_gix": "I2 Q3 KNN comparables (valuation)",
    "sale_parcel_date_ix": "I3 Q4 a parcel's sale history; Q3 lateral latest sale",
    "sale_date_brin": "I4 Q7 sales in a date range (vs a B-tree twin in the benchmark)",
    "pm_screener_ix": "I5 Q6 screener (covering, keyset)",
    "project_status_active_ix": "I6 partial: current status of active projects",
    "chunk_tsv_gin": "I7 Q8 keyword retrieval (full text)",
    "chunk_emb_hnsw": "I8 Q8 vector retrieval (cosine)",
    "village_name_trgm": "I9 Q9 fuzzy village search",
    "ledger_user_ix": "account ledger page (keyset)",
    "impact_project_ix": "Q2 impact_lookup variant",
    "app_user_email_uq": "case-insensitive unique email (login)",
    "pm_parcel_uq": "REFRESH ... CONCURRENTLY on mv_parcel_metrics; /parcels summary join",
}
DELETE = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}


def mb(b) -> str:
    return "-" if b in (None, "") else f"{float(b) / 1024 / 1024:,.2f}"


def int_(n) -> str:
    return "-" if n is None else f"{int(n):,}"


def read_csv(p: Path) -> list[dict]:
    return list(csv.DictReader(line for line in p.open() if not line.startswith("#"))) if p.exists() else []


def bench_rows() -> dict:
    out = {}
    for sf in ("1", "5"):
        for r in read_csv(RES / f"sf{sf}.csv"):
            out.setdefault((r["query"], r["variant"]), {})[sf] = r
    return out


def plan_type(r: dict | None) -> str:
    if not r:
        return "-"
    nodes = r.get("plan_nodes", "")
    idx = r.get("indexes_used", "")
    key = [n for n in nodes.split("|") if any(w in n for w in ("Scan", "Index"))]
    s = ", ".join(sorted(set(key))) or nodes.split("|")[0] if nodes else ""
    if idx:
        s += f" ({idx.split('|')[0]}{', ...' if '|' in idx else ''})"
    return s.replace("|", ", ")


def collect() -> dict:
    cat = {}
    for sf, db in DBS.items():
        tables = psql(db, TABLES_SQL)
        counts = psql(db, "SELECT json_build_object(" + ", ".join(f"'{t}', (SELECT count(*) FROM {t})" for t in tables) + ")")
        cat[sf] = {"tables": tables, "counts": counts, "indexes": psql(db, INDEX_SQL), "cons": psql(db, CONS_SQL),
                   "generated": psql(db, GEN_SQL), "mvs": psql(db, MV_SQL), "docs": psql(db, DOCS_SQL) or []}
    (PACK / "catalog").mkdir(parents=True, exist_ok=True)
    (PACK / "catalog" / "catalog.json").write_text(json.dumps(cat, indent=1, default=str))
    return cat


def explain_quote(q: str, sf: int, variant: str, patterns: list[str]) -> str:
    f = PACK / "explain" / f"explain_{q.lower()}_sf{sf}.txt"
    if not f.exists():
        return ""
    txt = f.read_text()
    m = re.search(rf"== {q} {re.escape(variant)}\b.*?(?=\n== |\Z)", txt, re.S)
    if not m:
        return ""
    lines = [ln.rstrip() for ln in m.group(0).splitlines() if any(re.search(p, ln) for p in patterns)]
    return "\n".join(lines[:8])


def main() -> int:
    PACK.mkdir(parents=True, exist_ok=True)
    cat = collect()
    b = bench_rows()
    md: list[str] = []
    w = md.append
    w("# LandLens report material (M8 pack)\n")
    w("Generated by `scripts/report_pack.py` from the live databases and the committed result files on 2026-11-24. "
      "Each figure names its source. SF1 = database `landlens_owner` (100k-parcel target), SF5 = `landlens_sf5` "
      "(500k). Not the report itself: raw material for it.\n")

    # 1. summary
    w("## 1. Project summary\n")
    w("**What is built** (source: `README.md`, the repository): Docker Compose stack (PostGIS 17 + pgvector, Martin "
      "tiles, FastAPI with raw SQL, Next.js, Caddy); a seeded synthetic data generator at scale factors 1 and 5; 15 "
      "numbered migrations (tables, partitions, indexes, materialized views, tile functions, roles); map + screener, "
      "parcel report with a rule-based valuation range, locality trends, credits with a ledger and a row-locked "
      "purchase transaction, document Q&A over 4 government acts with page citations; benchmarks Q1-Q9 at SF1 and "
      "SF5, pgbench, a concurrency harness and demo, backup/restore drill, security hardening.\n")
    w("**Scale: rows per base table** (source: `SELECT count(*)` on each table, live SF1 and SF5 databases, "
      "2026-11-24; also `report/pack/catalog/catalog.json`).\n")
    w("| Table | SF1 rows | SF5 rows |\n| --- | ---: | ---: |")
    for t in sorted(set(cat["SF1"]["tables"]) | set(cat["SF5"]["tables"])):
        w(f"| `{t}` | {int_(cat['SF1']['counts'].get(t))} | {int_(cat['SF5']['counts'].get(t))} |")
    w("\n| Materialized view | SF1 rows | SF1 size MB | SF5 rows | SF5 size MB |\n| --- | ---: | ---: | ---: | ---: |")
    m5 = {m["name"]: m for m in cat["SF5"]["mvs"]}
    for m in cat["SF1"]["mvs"]:
        o = m5.get(m["name"], {})
        w(f"| `{m['name']}` | {int_(m['rows'])} | {mb(m['bytes'])} | {int_(o.get('rows'))} | {mb(o.get('bytes'))} |")
    w("\n**Real vs synthetic** (source: `seed_inputs/sources.md`, `README.md`): real = the four government "
      "documents in `seed_inputs/docs/` and the OpenFreeMap base map. Synthetic = villages and boundaries, mandals, "
      "roads and water in LandLens's own layers, development projects and their status histories, master plan "
      "zones, parcels, sales and prices, guideline rates, soil and groundwater (no OSM export, projects GeoJSON or "
      "zone list was supplied; real OSM inputs are V1). Rows carry `source = 'synthetic'`; names start `[fallback]`.\n")

    # 2. schema
    w("## 2. Schema\n")
    w("Source: live catalog (`pg_constraint`, `pg_index`), `db/migrations/001-015`. Delete rules as stored "
      "(`confdeltype`). NO ACTION is Postgres's default and what the spec calls 'the default RESTRICT': both refuse "
      "to delete a referenced parent; NO ACTION checks at the end of the statement (deferrable), RESTRICT "
      "immediately. No FK that is part of a primary key uses SET NULL.\n")
    cons = cat["SF1"]["cons"]
    for grp, tabs in GROUPS.items():
        w(f"### {grp}\n")
        w("| Table | Primary key | Foreign keys (ON DELETE) | Unique |\n| --- | --- | --- | --- |")
        for t in tabs:
            if t not in cat["SF1"]["tables"]:
                continue
            pk = next((c["def"].replace("PRIMARY KEY ", "") for c in cons if c["tbl"] == t and c["contype"] == "p"), "-")
            fks = [f"{re.sub(r'FOREIGN KEY |REFERENCES ', '', c['def']).split(' ON ')[0]} ({DELETE[c['ondelete']]})"
                   for c in cons if c["tbl"] == t and c["contype"] == "f"]
            uq = [c["def"].replace("UNIQUE ", "") for c in cons if c["tbl"] == t and c["contype"] == "u"]
            w(f"| `{t}` | {pk} | {'; '.join(fks) or '-'} | {'; '.join(uq) or '-'} |")
        w("")
    other = sorted(set(cat["SF1"]["tables"]) - {t for v in GROUPS.values() for t in v})
    if other:
        w(f"Other tables: {', '.join(f'`{t}`' for t in other)} (bookkeeping).\n")
    w("**ER diagram:** `report/er-diagram.mmd` (Mermaid, generated by `make er` from the migrated schema; rendered "
      "as `figures/fig_er_diagram.png`). 23 LandLens tables (PostGIS's spatial_ref_sys and schema_migrations left out), 23 FK relationships; cardinality from FK nullability and "
      "uniqueness.\n")
    w("**Functional dependencies and normal forms** (source: spec 2.5, checked against the live schema):\n")
    w("| Table | Candidate keys | Key FDs | Normal form |\n| --- | --- | --- | --- |")
    for row in [
        ("village", "village_id", "village_id -> mandal_id, name, geom", "BCNF"),
        ("parcel", "parcel_id; (village_id, survey_no, sub_div)", "parcel_id -> all attributes", "BCNF (area_sqm, centroid generated)"),
        ("guideline_rate", "(village_id, land_class, effective_from)", "key -> rate_inr_per_sqm", "BCNF"),
        ("gw_assessment", "(mandal_id, assessment_year)", "key -> extraction_pct; extraction_pct -> category", "2NF by design (category generated)"),
        ("sale_transaction", "(txn_id, registered_on)", "txn_id -> all attributes", "BCNF"),
        ("parcel_zone", "(parcel_id, zone_id)", "key -> overlap_pct", "BCNF"),
        ("project_status_history", "(project_id, effective_from)", "key -> status", "BCNF"),
        ("app_user", "user_id; lower(email)", "user_id -> all attributes", "BCNF (cached credit_balance)"),
    ]:
        w(f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} |")
    w("\n`village.lgd_code` exists with a UNIQUE constraint (the spec's second candidate key) but is NULL for all "
      f"{int_(cat['SF1']['counts'].get('village'))} synthetic villages (no LGD codes without real village data); "
      "UNIQUE allows many NULLs, so `village_id` is the only key in practice.\n")
    w("**The three fixes from the FD analysis** (spec 2.5): (1) 2NF: `guideline_rate.unit` dropped because "
      "`land_class -> unit` was a partial dependency; every rate is INR per sq m. (2) 3NF: `sale_transaction` has "
      "no `village_id` (txn -> parcel -> village would be transitive); trends read it through "
      "`mv_village_price_index`. (3) Redundancy: `dev_project` has no `status` / `announced_on`; both derive from "
      "`project_status_history` (the API computes `announced_on` as the first status date, migration-free).\n")
    w("**Controlled exceptions:** generated columns (source: `pg_attribute.attgenerated`, live SF1):\n")
    for g in cat["SF1"]["generated"] or []:
        w(f"- `{g['tbl']}.{g['col']}` = `{' '.join(g['expr'].split())[:160]}`")
    w("\n- `app_user.credit_balance` caches `SUM(credit_ledger.delta)` so a purchase locks one row and a `CHECK` "
      "blocks negatives; reconciled in tests and in `bench/results/concurrency_unlock.json` "
      "(`balance_equals_ledger_sum: true`) and `bench/results/restore_drill.txt` (sum credit_balance = sum ledger "
      "delta = 10).\n")

    # 3. indexes
    w("## 3. Indexes\n")
    w("Source: `pg_index` + `pg_relation_size` summed over partitions (`pg_partition_tree`), live SF1 and SF5.\n")
    w("| Index | Table | Type | Serves | SF1 MB | SF5 MB |\n| --- | --- | --- | --- | ---: | ---: |")
    i5 = {i["name"]: i for i in cat["SF5"]["indexes"]}
    for i in cat["SF1"]["indexes"]:
        if i["name"].endswith("_pkey") or i["name"].endswith("_key"):
            continue
        serves = INDEX_QUERY.get(i["name"], "REFRESH CONCURRENTLY key" if "price_index" in i["tbl"] else "")
        w(f"| `{i['name']}` | `{i['tbl']}` | {i['type']} | {serves} | {mb(i['bytes'])} | {mb(i5.get(i['name'], {}).get('bytes'))} |")
    pk_total = sum(float(i["bytes"] or 0) for i in cat["SF1"]["indexes"] if i["name"].endswith(("_pkey", "_key")))
    w(f"\nPrimary-key and unique-constraint indexes (not listed): {mb(pk_total)} MB at SF1.\n")

    # 4. benchmarks
    w("## 4. Benchmarks\n")
    w("Source: `bench/results/sf1.csv` (2026-11-24, clean SF1 seed) and `bench/results/sf5.csv` (2026-11-24, SF5 "
      "re-seed). Method: EXPLAIN (ANALYZE, BUFFERS), warm cache, median of 10 runs after 2 warm-ups (slow variants "
      "> 20 s: 3 runs). Plans: `report/pack/explain/explain_q*_sf{1,5}.txt`. Charts: `figures/fig_q*.png`.\n")
    titles = {"Q1": "point-in-parcel", "Q2": "parcels near an active project", "Q3": "10 nearest comparables",
              "Q4": "a parcel's sale history", "Q5": "village yearly medians", "Q6": "screener page",
              "Q7": "sales in a date range", "Q8": "document retrieval", "Q9": "fuzzy village search"}
    for q in [f"Q{i}" for i in range(1, 10)]:
        rows = [(v, d) for (qq, v), d in b.items() if qq == q]
        if not rows:
            continue
        w(f"### {q} {titles[q]}\n")
        w("| Variant | SF1 median ms | SF5 median ms | Plan (SF1) | Index size MB (SF1 / SF5) |\n| --- | ---: | ---: | --- | --- |")
        for v, d in rows:
            s1, s5 = d.get("1"), d.get("5")
            med = lambda r: r["median_ms"] if r and r.get("median_ms") else ("-" if not r else (r.get("note") or "-")[:40])  # noqa: E731
            size = f"{(s1 or {}).get('index_size_mb') or '-'} / {(s5 or {}).get('index_size_mb') or '-'}"
            w(f"| {v} | {med(s1)} | {med(s5)} | {plan_type(s1)} | {size} |")
        w("")
    def m(q, v, sf):  # noqa: E306
        r = b.get((q, v), {}).get(sf)
        return float(r["median_ms"]) if r and r.get("median_ms") else None
    w("### Stories the numbers tell\n")
    w(f"- **Q2 ST_Subdivide.** GiST on parcels cuts the full scan ({m('Q2','no_index','1'):,.0f} -> "
      f"{m('Q2','gist','1'):,.0f} ms at SF1, {m('Q2','no_index','5'):,.0f} -> {m('Q2','gist','5'):,.0f} ms at SF5), but "
      f"what remains is the exact ST_DWithin test against two large, complex project polygons (the airport site "
      f"and the textile park, the only active projects): explain_q2_sf5 shows 110,150 candidate pairs from 2 "
      f"projects. Splitting the project geometry into 18 small pieces (ST_Subdivide on ST_Segmentize, own GiST) "
      f"gives more pairs (464,630) but each test is cheap: {m('Q2','gist_subdivided','1'):,.0f} / "
      f"{m('Q2','gist_subdivided','5'):,.0f} ms (1.3x / 1.8x faster than plain GiST). The precomputed "
      f"`parcel_project_impact` lookup skips geometry entirely: {m('Q2','impact_lookup','1'):,.0f} / "
      f"{m('Q2','impact_lookup','5'):,.0f} ms (it measures from parcel centroids, so its count differs slightly from "
      f"the geometry variants). Before the M5 data change (5 active projects including two ring roads) plain GiST "
      f"helped far less, because a ring road's bounding box covers most of the core (earlier SF1 run, recorded in the build notes).")
    w(f"- **Q6 selective vs broad.** With the covering index I5, a selective filter returns page 1 in "
      f"{m('Q6','mv_covering_selective_page1','1')} / {m('Q6','mv_covering_selective_page1','5')} ms (SF1 / SF5) "
      f"against {m('Q6','mv_no_covering_selective_page1','1')} / {m('Q6','mv_no_covering_selective_page1','5')} ms "
      f"without it. For the broad filter the gain is smaller ({m('Q6','mv_covering_page1','1')} vs "
      f"{m('Q6','mv_no_covering_page1','1')} ms at SF1, {m('Q6','mv_covering_page1','5')} vs "
      f"{m('Q6','mv_no_covering_page1','5')} ms at SF5): the index orders by (land_type, zone_code, cagr_5y) but "
      f"the filter ranges over several zones and a distance, so many index entries are read and then filtered "
      f"(explain_q6_sf5: 'Rows Removed by Filter: 32646' per worker).")
    w(f"- **Keyset vs OFFSET.** Page 50 with keyset: {m('Q6','mv_covering_page50_keyset','1')} / "
      f"{m('Q6','mv_covering_page50_keyset','5')} ms; with OFFSET 2450: {m('Q6','mv_covering_page50_offset','1')} / "
      f"{m('Q6','mv_covering_page50_offset','5')} ms. OFFSET must produce and discard 2,450 rows (top-N heapsort "
      f"memory grows from ~31 kB to ~550-715 kB in explain_q6_sf5); keyset starts at the cursor.")
    w(f"- **BRIN vs B-tree (Q7).** BRIN {m('Q7','brin','1')} / {m('Q7','brin','5')} ms, B-tree "
      f"{m('Q7','btree','1')} / {m('Q7','btree','5')} ms, no index {m('Q7','no_index','1')} / "
      f"{m('Q7','no_index','5')} ms. Yearly partitions already prune to one year, so BRIN's block ranges save little "
      f"and its lossy bitmap rechecks rows: BRIN is slower than both the B-tree and a plain scan of the partition at SF1 and SF5. Its advantage is size: 0.45 MB against 2.66 / 12.44 MB for the B-tree twin.")
    w(f"- **Q8 retrieval (149 chunks).** Keyword {m('Q8','keyword_gin','1')} ms, exact vector scan "
      f"{m('Q8','vector_exact','1')} ms, HNSW {m('Q8','vector_hnsw','1')} ms, spec hybrid {m('Q8','hybrid_rrf','1')} ms, "
      f"the API's statement {m('Q8','hybrid_api_statement','1')} ms (SF1). "
      + "".join(f"HNSW {r['note']} vs the exact scan (avg of 20 query vectors). "
                for (q, v), d in b.items() if q == "Q8" and v == "hnsw_recall_at_10" for r in [d.get('1', {})])
      + "On 149 chunks the planner scans the table for the keyword query too (GIN unused). Retrieval quality per method is in section 7.")
    w(f"- **Index bloat from REFRESH CONCURRENTLY.** The benchmark measured `pm_screener_ix` at 33.95 / 89.48 MB "
      f"(sf*.csv, index_size_mb) after many concurrent refreshes during the build; migration 015 later recreated the "
      f"view and the fresh index is {mb(next(i['bytes'] for i in cat['SF1']['indexes'] if i['name'] == 'pm_screener_ix'))} / "
      f"{mb(next(i['bytes'] for i in cat['SF5']['indexes'] if i['name'] == 'pm_screener_ix'))} MB (section 3). "
      f"CONCURRENTLY rewrites changed rows instead of swapping the heap, so its indexes bloat; a periodic REINDEX "
      f"CONCURRENTLY or a plain REFRESH in a maintenance window reclaims it.")
    w("")
    w("### pgbench: screener page 1, random growth threshold, 30 s per run\n")
    w("Source: `bench/results/pgbench_landlens_owner.csv` (SF1), `bench/results/pgbench_landlens_sf5.csv` (SF5); "
      "script `bench/pgbench/screener.sql`.\n")
    w("| Scale | Clients | TPS | Avg latency ms | Transactions |\n| --- | ---: | ---: | ---: | ---: |")
    for sf, f in (("SF1", "pgbench_landlens_owner.csv"), ("SF5", "pgbench_landlens_sf5.csv")):
        for r in read_csv(RES / f):
            w(f"| {sf} | {r['clients']} | {float(r['tps']):,.1f} | {r['latency_avg_ms']} | {int_(r['transactions'])} |")
    w("")
    w("### Results that need explaining (planner's reason from EXPLAIN)\n")
    q3 = explain_quote("Q3", 5, "knn", [r"JIT:", r"Timing: Generation", r"Execution Time", r"Limit  \(cost"])
    w(f"1. **Q3 KNN comparables is {m('Q3','knn','5'):,.0f} ms at SF5 ({m('Q3','knn','1'):,.0f} at SF1, of which JIT ~81 ms in explain_q3_sf1), but the query "
      "work is ~2 ms: the time is JIT compilation.** The plan touches 20 parcels and 364 buffers, yet the "
      "planner's total cost estimate (619,100, from the LIMIT over a KNN scan with a per-row LATERAL) exceeds "
      "`jit_above_cost` (100,000), so Postgres JIT-compiles 48 functions. Same prepared query on SF5 with "
      "`jit = on`: 1,086 ms (JIT total 1,051 ms); with `SET jit = off`: 1.9 ms (manual EXPLAIN ANALYZE, "
      "2026-11-24). Fix: `jit = off` (or a much higher `jit_above_cost`) for this OLTP workload; not applied, so "
      "the committed numbers stay comparable. The report endpoint's comparables query has the same shape.\n"
      f"```\n{q3}\n```")
    q3o = explain_quote("Q3", 5, "order_by_st_distance", [r"Nested Loop \(", r"rows=1649", r"Execution Time", r"Timing: Generation"])
    w(f"2. **Q3 ORDER BY ST_Distance** ({m('Q3','order_by_st_distance','5'):,.0f} ms at SF5): without the `<->` "
      "operator the planner cannot use KNN; it fetches every parcel within 5 km (165k at SF5), runs the LATERAL "
      "sale lookup for each, then sorts. JIT adds ~1.9 s at SF5 here too.\n"
      f"```\n{q3o}\n```")
    q7 = explain_quote("Q7", 5, "brin", [r"Heap Blocks", r"Rows Removed by Index Recheck", r"Execution Time"])
    w(f"3. **BRIN slower than the B-tree and than a plain scan (Q7).** Partition pruning leaves one year (the 2024 "
      "partition, 1,178 pages at SF5); BRIN marks 410 of them as candidates (lossy) and rechecks 10,277 rows away, "
      "while the B-tree reads ~317 buffers exactly.\n"
      f"```\n{q7}\n```")
    q9 = explain_quote("Q9", 1, "trigram_gin", [r"Seq Scan", r"Execution Time"])
    w("4. **Q9 trigram index unused.** `village` has 185 rows (one or two pages); a sequential scan is cheaper "
      "than any index lookup, so the GIN index only matters at larger village counts.\n"
      f"```\n{q9}\n```")
    w(f"5. **Q8 HNSW vs exact.** With 149 chunks the exact scan is ~{m('Q8','vector_exact','1')} ms; the benchmark "
      "forces the index (`enable_seqscan = off`) to measure HNSW, and recall@10 is 1.0. The index pays off only at "
      "thousands of chunks.\n")
    w("6. **pgbench levels off.** From 8 to 32 clients throughput rises only 16% at SF1 (279 -> 324 TPS) while "
      "average latency grows 3.4x (29 -> 99 ms), so the server is already near capacity at 8 clients; extra clients "
      "queue. pgbench ran inside the db container on the same 12-core laptop as the stack. Each transaction is a "
      "broad screener page (peri-urban, within 3 km, a random growth floor), which reads thousands of index entries: "
      "the benchmark's Q6 page 1 at SF1 keeps 11,447 and filters 5,325 (explain_q6_sf1); pgbench's own filter "
      "differs, so this shows the order of magnitude only (source: pgbench CSVs above).\n")

    # 5. transactions
    w("## 5. Transactions\n")
    w("**Purchase transaction** (spec 2.11; implemented in `api/landlens/app/routers/credits.py`), READ COMMITTED:\n")
    w("```sql\nBEGIN;\nSELECT credit_balance FROM app_user WHERE user_id = $u FOR UPDATE;   -- serializes this user's purchases\n"
      "-- already unlocked -> COMMIT, charged 0;  credit_balance < 1 -> ROLLBACK, 402\n"
      "INSERT INTO report_unlock (user_id, parcel_id, credits_spent) VALUES ($u, $p, 1);\n"
      "INSERT INTO credit_ledger (user_id, delta, reason, parcel_id, idempotency_key) VALUES ($u, -1, 'report_unlock', $p, $key);\n"
      "UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = $u;\nCOMMIT;\n```\n")
    demo = (RES / "concurrency_demo.txt").read_text().splitlines()
    keep = [ln for ln in demo if "--" in ln or "40001" in ln or "FOR UPDATE" in ln or "got the lock" in ln][:14]
    w("**Three-version demo** (source: `bench/results/concurrency_demo.txt`, `concurrency_demo.json`; `make "
      "demo-concurrency`). Excerpt:\n")
    w("```\n" + "\n".join(keep) + "\n```")
    cj = json.loads((RES / "concurrency_demo.json").read_text())
    w(f"Results: broken -> final balance {cj['broken']['final_balance']} (expected {cj['broken']['expected']}, lost "
      f"update); row lock -> {cj['row_lock']['final_balance']}, B waited {cj['row_lock']['b_waited_s']} s and saw "
      f"{cj['row_lock']['b_saw']}, ledger sum {cj['row_lock']['ledger_sum']}; SERIALIZABLE -> "
      f"{cj['serializable']['final_balance']} after SQLSTATE {cj['serializable']['sqlstate']} and "
      f"{cj['serializable']['attempts']} attempts.\n")
    cu = json.loads((RES / "concurrency_unlock.json").read_text())
    w(f"**1,000 parallel unlocks** (source: `bench/results/concurrency_unlock.json`, `make concurrency`): "
      f"{cu['requests']} requests by a user with {cu['credits']} credits through Caddy; statuses {cu['statuses']}; "
      f"wall {cu['wall_s']} s, p50 {cu['latency_ms']['p50']} ms, p95 {cu['latency_ms']['p95']} ms; database: "
      f"{cu['db']}; all {len(cu['checks'])} checks {'pass' if cu['pass'] else 'FAIL'} "
      f"({', '.join(k for k, v in cu['checks'].items() if v)}).\n")
    w("**Idempotency** (source: `api/tests/test_credits.py`, `credits.py`): Idempotency-Key header required (422 "
      "without; 422 if not a UUID); the same key replayed for the same parcel returns charged 0; the same key for "
      "a different parcel -> 409 `idempotency_key_reused`; the `report_unlock` primary key is the second guard; "
      "replaying the 10 winning requests in the load test charged 0 (`replays_charge_0`). The UI keeps one key per "
      "attempt and reuses it after a network error or 503.\n")

    # 6. recovery
    w("## 6. Recovery\n")
    w("Source: `bench/results/restore_drill.txt` (`make backup` then `make restore`).\n")
    w("```\n" + (RES / "restore_drill.txt").read_text().strip() + "\n```\n")
    w("The drill ran before migration 015 was applied (hence 14 schema_migrations; the live database now has 15). "
      "Point-in-time recovery (spec stretch) was not done.\n")

    # 7. RAG
    w("## 7. RAG\n")
    w("**Corpus** (source: `document` / `document_chunk`, live SF1; pages without a text layer from "
      "`seed_inputs/docs/embeddings/*.json` `flagged_pages`):\n")
    w("| Document | Pages | Chunks | ~Tokens |\n| --- | ---: | ---: | ---: |")
    for d in cat["SF1"]["docs"]:
        w(f"| {d['title']} | {d['pages']} | {d['chunks']} | {int_(d['tokens_est'])} |")
    dumps = {json.loads(p.read_text())["title"]: json.loads(p.read_text()).get("flagged_pages", [])
             for p in (ROOT / "seed_inputs" / "docs" / "embeddings").glob("*.json")}
    for t, fp in dumps.items():
        if fp:
            w(f"\n{t}: pages {fp} have no text layer and are skipped (no OCR).")
    w("\n**Retrieval design** (source: `api/landlens/app/services/rag.py`, spec 2.13, ADR-012): PyMuPDF text blocks, "
      "~400-token chunks with 15% overlap, cut early at headings; `text-embedding-3-small` (1536 dims). One SQL "
      "statement fuses the top 40 keyword candidates (`ts_rank_cd` over a GIN `tsvector`) and the top 40 vector "
      "candidates (HNSW cosine) by Reciprocal Rank Fusion (k = 60), returns the top 6 plus the keyword hit count and "
      "the best cosine distance. Generation (`LLM_MODEL`, default gpt-4o-mini, temperature 0) sees only numbered "
      "excerpts; every `[n]` is checked against the excerpts given; unknown numbers are dropped, none left -> "
      "excerpts without an answer. No key or an outage -> degraded keyword-only mode (same statement, OR-ed terms).\n")
    w("**Not-found rule:** no keyword hit AND best cosine distance > 0.6 (`CHAT_MAX_DISTANCE`) -> \"not found in "
      "the documents\" without calling the LLM.\n")
    ev = json.loads((RES / "rag_eval.json").read_text())
    s = ev["summary"]
    w(f"**Eval** (source: `bench/results/rag_eval.json`, the latest `make eval` run, 2026-11-23, {s['model']}, "
      f"threshold {s['max_distance']}; questions in `bench/rag_eval_questions.json`, 20 answerable + 5 not):\n")
    w(f"| Metric | Value |\n| --- | --- |\n| Citation correctness (answerable with >= 1 citation on an expected page) | "
      f"{s['citation_correct_pct']}% |\n| All citations correct | {s['all_citations_correct_pct']}% |\n| Refusal "
      f"accuracy (unanswerable -> not found) | {s['refusal_accuracy_pct']}% |\n| Recall@10 keyword / vector / hybrid | "
      f"{s['recall_at_10_pct']['keyword']}% / {s['recall_at_10_pct']['vector']}% / {s['recall_at_10_pct']['hybrid']}% |\n"
      f"| Mean seconds per question | {s['mean_seconds']} |\n| Spec target (>= 80% citations, every refusal) | "
      f"{'met' if s['target_met'] else 'not met'} |\n")
    # offline re-score with the answer checks added later (no API call)
    src = (ROOT / "bench" / "rag_eval.py").read_text()
    ns: dict = {}
    exec(src[src.index("def facts_ok"):src.index("def overlaps")], ns)
    qs = {q["id"]: q for q in json.loads((ROOT / "bench" / "rag_eval_questions.json").read_text())["questions"]}
    ans = [r for r in ev["results"] if r["answerable"]]
    ok = [r["id"] for r in ans if r["correct"] and ns["facts_ok"](r["answer"], qs[r["id"]])[0]]
    bad = [f"{r['id']} ({'; '.join(ns['facts_ok'](r['answer'], qs[r['id']])[1]) or 'wrong citation page'})"
           for r in ans if r["id"] not in ok]
    dists_a = [r["best_distance"] for r in ans if r["best_distance"] is not None]
    dists_u = [r["best_distance"] for r in ev["results"] if not r["answerable"] and r["best_distance"] is not None]
    w(f"Answer correctness, re-scored offline from the same saved answers with the phrase checks added on "
      f"2026-11-24 (`facts_ok` in `bench/rag_eval.py`): **{len(ok)}/{len(ans)}**. Misses: {', '.join(bad)}. "
      "The prompt rules added after this run (yes/no conditions, officer names, no chained routes) have not been "
      "re-measured: `make eval` was not run again.\n")
    w(f"Best cosine distance: answerable {min(dists_a):.3f}-{max(dists_a):.3f}, unanswerable "
      f"{min(dists_u):.3f}-{max(dists_u):.3f}; the ranges overlap, so the 0.6 gate skipped the LLM for only "
      f"{sum(d > 0.6 for d in dists_u)} of {len(dists_u)} unanswerable questions; the LLM refused the rest.\n")

    # 8. security
    w("## 8. Security\n")
    w("Source: `SECURITY.md` (verbatim table), checked by `make security-check` (21 checks, all OK on the normal "
      "stack and in the fresh-machine test) and `make audit` (13 Python pins + 243 npm lockfile packages, 0 known "
      "vulnerabilities, 2026-11-24).\n")
    sec = (ROOT / "SECURITY.md").read_text()
    tbl = re.search(r"\| Threat \| Control \| Where \|.*?(?=\n\n)", sec, re.S)
    w(tbl.group(0) + "\n" if tbl else "")

    # 9. tiles, fresh machine
    w("## 9. Tile weight and fresh-machine test\n")
    tiles = read_csv(RES / "tile_weight_sf1.csv")
    before = {"14/11814/7360": 574046, "14/11810/7360": 579469, "14/11812/7358": 423532}
    w("Source: `bench/results/tile_weight_sf1.csv` (after migration 014; 'before' figures from its comment line, "
      "spec 2.8 tile).\n")
    w("| Tile | Parcels | Before raw KB | After raw KB | After gzip KB | Warm s |\n| --- | ---: | ---: | ---: | ---: | ---: |")
    for r in tiles[:6]:
        bf = before.get(r["tile"])
        w(f"| {r['tile']} | {int_(r['parcels'])} | {f'{bf / 1024:,.0f}' if bf else '-'} | {int(r['raw_bytes']) / 1024:,.0f} | "
          f"{int(r['gzip_bytes']) / 1024:,.0f} | {float(r['gzip_warm_s']):.3f} |")
    w("\nTarget: under 150 KB per dense tile; met at z14 (merge per heat class, half-pixel simplification) and z15 "
      "(one feature per parcel, feature id instead of attributes).\n")
    w("**Fresh-machine test** (source: the fresh-machine test record in `README.md` and its commit message): zip unzipped into a new folder, own "
      "Compose project, README followed word for word, no `.env` until `make up` created one: `make up` 1.9 min + "
      "`make seed SF=1` 2.7 min = 4.6 min with Docker base images already present; demo login, screener "
      "(99,483 -> 6,692), report unlock (10 -> 9 credits), trends, degraded chat with a PDF citation, `make test` "
      "(51 passed), `make demo-concurrency`, `make security-check`: all OK, no console errors. On a machine "
      "without the base images: allow 10-20 min for the first build (estimate).\n")

    # 10. limitations
    w("## 10. Known limitations and V1\n")
    w("Source: the build notes' known issues, `SECURITY.md` residual risks, the V1 roadmap.\n")
    for x in [
        "All land data is synthetic (no OSM export, projects GeoJSON or zone list supplied); price bases are placeholders, not calibrated to published Warangal rates.",
        "JIT compilation dominates the comparables (KNN) query at SF5 (~0.9 s of ~0.9 s); `jit = off` would fix it (not applied).",
        "BRIN on sale dates is slower than a B-tree on yearly partitions; kept for size and as a measured comparison.",
        "Corpus: no G.O.Ms.No.202 / KUDA zoning regulations, so zone-specific rules (setbacks, permitted uses) are usually 'not found'; AP Act 2006 pages 7-12 have no text layer (no OCR); the Bhu Bharati Act is a noisy OCR scan.",
        "RAG: keyword recall@10 only 30% (websearch AND semantics), so hybrid adds nothing over vector on this eval; 4/20 answers wrong or partly wrong in the last eval; the prompt fix is unmeasured.",
        "Security residuals: no HTTPS locally; CSP keeps script-src 'unsafe-inline'; rate limits in memory per worker; JWTs not revocable before expiry; Swagger public unless API_DOCS=false.",
        "Agricultural parcels (146 at SF1) sit mostly in one village; their cagr_5y distribution is narrow.",
        "No point-in-time recovery demo; watchlist (stretch) not built; responsive layout below 900 px not walked; J3 not walked live with a key by the agent.",
    ]:
        w(f"- {x}")
    w("\n**V1** (spec 3.6): scraping pipeline (guideline rates, KUDA/MA&UD orders, project news) after a terms-of-use "
      "review, through the existing staging/upsert path; real OSM, project geometry and zone legend inputs; "
      "watchlist alerts (event table matched against watchlists, email); ML valuation (gradient-boosted quantiles, "
      "SHAP drivers) only if it beats the rule-based baseline on real data; parcel chat over parameterized queries; "
      "PDF highlighting; Razorpay test mode and PDF export; hosted VPS with HTTPS and HSTS, Playwright smoke tests, "
      "mobile layout; nonce-based CSP; token revocation.\n")

    # 11. figures
    captions = {
        "fig_benchmarks_overview": "Slowest vs fastest variant per query, SF1 and SF5, log scale (bench/results/sf*.csv)",
        "fig_q1_point_in_parcel": "Q1 point-in-parcel: sequential scan vs GiST",
        "fig_q2_subdivide": "Q2 parcels near an active project: no index, GiST, partial GiST, ST_Subdivide pieces, impact table",
        "fig_q3_knn_comparables": "Q3 comparables: ORDER BY ST_Distance vs KNN (<->); both times include JIT (section 4)",
        "fig_q4_sale_history": "Q4 sale history: sequential scan vs composite B-tree",
        "fig_q5_matview_vs_aggregation": "Q5 village medians: raw aggregation vs materialized view, plus REFRESH CONCURRENTLY",
        "fig_q6_screener_covering_keyset": "Q6 screener: base joins, view without/with covering index, OFFSET vs keyset, selective filter",
        "fig_q7_brin_vs_btree": "Q7 date range: no index vs B-tree vs BRIN",
        "fig_q8_retrieval": "Q8 retrieval on 149 chunks: keyword, exact vector, HNSW, hybrid (spec), the API statement",
        "fig_q9_village_search": "Q9 fuzzy village search: ILIKE vs trigram GIN",
        "fig_tile_weight": "Dense z14 parcel tile size before/after migration 014 (bench/results/tile_weight_sf1.csv)",
        "fig_pgbench_screener": "pgbench screener throughput at 8 and 32 clients, SF1 and SF5",
        "fig_er_diagram": "ER diagram rendered from report/er-diagram.mmd (23 tables, 23 FKs)",
        "fig_screen_landing": "Landing page (light)",
        "fig_screen_map_screener": "Map + screener: peri-urban, within 3 km of an active project, >= 15%/yr -> 4,951 parcels; parcel card open (light)",
        "fig_screen_map_screener_dark": "Map + screener, same filters (dark)",
        "fig_screen_parcel_report": "Unlocked parcel report: tiles, valuation range and drivers, price history, comparables, zoning, soil and water (light)",
        "fig_screen_parcel_report_dark": "Unlocked parcel report (dark)",
        "fig_screen_trends": "Locality trends: median with the p25-p75 band, guideline, sales-per-year bars (light)",
        "fig_screen_chat_citation_keyword_mode": "Chat with citations, live, API without an OpenAI key: keyword-only mode with page citations (light)",
        "fig_screen_chat_answer_replay": "Chat answer REPLAYED from bench/results/rag_eval.json (question A16, gpt-4o-mini, 2026-11-23): the saved answer and citation rendered by the UI via a browser-side stub, with the real cited chunk from the database; not a live call (light)",
    }
    w("## 11. Figures\n")
    w("PNG at 2x in `figures/` (charts from `bench/charts/*.svg`, ER diagram via Mermaid 12.3.0, screenshots of the "
      "production build at http://localhost, 1440 px wide). Screenshot data is synthetic.\n")
    w("| File | Caption |\n| --- | --- |")
    for f in sorted((PACK / "figures").glob("*.png")):
        w(f"| `figures/{f.name}` | {captions.get(f.stem, '')} |")
    w("\nOther files in the pack: `er-diagram.mmd` (diagram source), `explain/explain_q*_sf{1,5}.txt` (EXPLAIN "
      "ANALYZE output quoted above), `catalog/catalog.json` (the catalog data behind sections 1-3).\n")

    (PACK / "report_material.md").write_text("\n".join(md) + "\n")
    print(f"wrote {PACK / 'report_material.md'} ({len(md)} blocks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
