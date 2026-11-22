"""`landlens` CLI (spec 2.2 jobs, FR-13). Runs inside the api image: `docker compose run --rm api landlens ...`."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="landlens", description="LandLens data jobs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("migrate", help="apply numbered SQL migrations (spec 2.17)")
    p.add_argument("--phase", choices=("schema", "post-load", "all"), default="schema")
    p = sub.add_parser("gen", help="generate the synthetic dataset over real geography (spec 2.12)")
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
    sub.add_parser("ingest-pdf", help="ingest the corpus PDFs (M5, not implemented yet)")
    sub.add_parser("bench", help="run benchmarks (M2, not implemented yet)")
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
        for step in (lambda: migrate.run("schema"), lambda: run(a.sf, a.seed), lambda: migrate.run("post-load"),
                     maintenance.refresh, maintenance.verify):
            rc = step()
            if rc:
                return rc
        return 0
    if a.cmd in ("refresh", "partitions", "verify", "checksum"):
        return getattr(maintenance, a.cmd)()
    print(f"landlens {a.cmd}: not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
