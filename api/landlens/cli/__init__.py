"""`landlens` CLI (spec 2.2 jobs, FR-13). Runs inside the api image: `docker compose run --rm api landlens ...`."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="landlens", description="LandLens data jobs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("migrate", help="apply numbered SQL migrations (spec 2.17)")
    p.add_argument("--phase", choices=("schema", "post-load", "all"), default="schema")
    p = sub.add_parser("gen", help="generate the synthetic dataset (spec 2.12); without seed_inputs OSM/projects/zones every layer is a fallback")
    p.add_argument("--sf", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    sub.add_parser("osm-load", help="check the Overpass export in seed_inputs/osm (loaded by gen, step 1)")
    p = sub.add_parser("seed", help="schema phase, gen, post-load phase, refresh, verify (spec 2.17)")
    p.add_argument("--sf", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    sub.add_parser("refresh", help="refresh materialized views concurrently, in dependency order")
    sub.add_parser("partitions", help="create next year's sale_transaction partition")
    sub.add_parser("verify", help="M1 verification: row counts, spatial consistency, invalid geometry, point query")
    sub.add_parser("checksum", help="per-table content checksums (determinism)")
    p = sub.add_parser("ingest-pdf", help="parse, chunk, embed and insert the corpus PDFs (spec 2.13), idempotent by sha256")
    p.add_argument("paths", nargs="*", help="PDF files or folders (default: seed_inputs/docs)")
    p.add_argument("--dry-run", action="store_true", help="parse and chunk only; print pages, chunks, tokens, cost")
    p.add_argument("--offline", action="store_true", help="only documents with an embeddings dump (no OpenAI call)")
    p.add_argument("--fake-embeddings", action="store_true", help="local hash vectors, for pipeline tests only")
    p.add_argument("--dump-dir", help="embeddings dump folder (default: seed_inputs/docs/embeddings)")
    p = sub.add_parser("bench", help="run the Q1-Q9 benchmarks (spec 2.19); writes bench/results/sf<N>.csv")
    p.add_argument("queries", nargs="*", help="optional subset, e.g. Q1 Q6")
    a = ap.parse_args(argv)

    from . import maintenance, migrate

    if a.cmd == "migrate":
        return migrate.run(a.phase)
    if a.cmd == "gen":
        from landlens.gen import run
        return run(a.sf, a.seed)
    if a.cmd == "osm-load":
        from landlens.gen.geo import seed_inputs
        files = sorted((seed_inputs() / "osm").glob("*.json"))
        print("\n".join(str(f) for f in files) or "no Overpass export in seed_inputs/osm/: gen uses the synthetic fallback")
        return 0
    if a.cmd == "seed":
        from landlens.gen import run

        from . import ingest
        # documents are truncated with the other data tables; restore them from the embeddings dumps (free)
        for step in (lambda: migrate.run("schema"), lambda: run(a.sf, a.seed), lambda: migrate.run("post-load"),
                     maintenance.refresh, maintenance.verify, lambda: ingest.run([], offline=True) and 0):
            rc = step()
            if rc:
                return rc
        return 0
    if a.cmd == "bench":
        import os
        import runpy
        bench = os.environ.get("LANDLENS_BENCH_DIR", "/app/bench")
        return runpy.run_path(f"{bench}/runner.py", run_name="landlens_bench")["main"](a.queries)
    if a.cmd == "ingest-pdf":
        from . import ingest
        return ingest.run(a.paths, dry_run=a.dry_run, offline=a.offline, fake=a.fake_embeddings, dump_dir=a.dump_dir)
    if a.cmd in ("refresh", "partitions", "verify", "checksum"):
        return getattr(maintenance, a.cmd)()
    print(f"landlens {a.cmd}: not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
