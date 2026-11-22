# LandLens handoff (M0-M2, 2026-11-22)

Spec: `docs/` (PRD, Tech Spec, Roadmap, ADRs). Owner decisions `registry/decisions/DEC-*` override it.

## Built and working
- **M0** Compose stack: db (PostGIS 17-3.6 + pgvector 0.8.7), martin 1.16.1, api (FastAPI, `/api/health`),
  web (Next.js 15.5.29, lockfile), caddy 2.11.8 on :80. Only Caddy publishes a port.
- **M1** Migrations 001-009 + 013 (23 tables, enums, yearly sale partitions, roles, `landlens_as_of()`);
  `landlens migrate` with checksums and phases (spec 2.17); seeded generator (spec 2.12 steps 1-12); demo
  account; `landlens verify` (row counts, 0 spatial failures, 0 invalid geometries, point query, demo ledger).
- **M2** 010 indexes, 011 views + I5 (`mv_village_price_index`, `mv_parcel_metrics`, `mv_mandal_price_index`),
  012 tile functions (parcels, villages, zones, projects, infra, coverage); Q1-Q9 runner with results in
  `bench/results/sf1.csv` and `sf5.csv` (Q8 skipped until M5).

## How to run (from landlens/, with your .env)
```
make up            # build, start; one-shot `migrate` service runs the schema phase (~45 s)
make seed SF=1     # schema -> gen -> post-load (010-012) -> refresh -> verify; restarts martin (~2 min)
make verify        # M1 checks
make bench         # Q1-Q9 at the main DB's SF (~5 min at SF1)
make seed-sf5 && make bench-sf5   # second database landlens_sf5 (~10 min + ~30 min)
```
Tiles: `http://localhost/tiles/{tiles_parcels|tiles_villages|...}/{z}/{x}/{y}`; catalog at `/tiles/catalog`.
Demo login: demo@landlens.local / demolandlens (local only; 10 credits).

## Decisions made outside the spec
| Decision | Commit |
| --- | --- |
| db `listen_addresses = '*'` in the custom postgresql.conf (mirrors the base image) | d653f4c |
| npm `overrides.postcss`: next 15.5.29 bundles postcss 8.4.31 (advisories); forced to 8.5.32 | dee0d37 |
| All 4326 -> 32644 transforms in PostGIS (no pyproj) | ff82d5b |
| Price base B = 2025 price level (growth index = 1 in 2025); sale cut-off fixed at 2026-10-31 | ff82d5b |
| A seed resets every data table, including users; the demo account is re-created each time | ff82d5b, da7df12 |
| Demo window computed (core r, corridors r/3) so expected parcels at target sizes = SF target; radii in `parcel_coverage` (migration 008). SF1 r=1.06 km, SF5 r=3.80 km | da7df12 |
| 013 creates roles without passwords; `landlens migrate` sets them from LANDLENS_*_PASSWORD | 97e1103 |
| One-shot `migrate` compose service before martin/api; martin as `landlens_tiles`, functions only | 616c378 |
| `tiles_coverage` source; `landlens_tiles` also reads `parcel_coverage` (DEC-004 consequence) | 616c378 |
| Bench variants run in rolled-back transactions; baselines are index-free (Q2 drops project_geom_gix, Q7 disables index scans) | a824ca7 |
| Slow bench variants (> 20 s): 1 warm-up + 3 runs; timeouts recorded, not fatal | 26bff4e |

## Open fallbacks (all `source='synthetic'`, names `[fallback] ...`; see `seed_inputs/README.md`)
- `seed_inputs/osm/*.json`: missing -> synthetic villages, radial roads, road grid, tanks, amenities.
  Produce with `api/landlens/gen/overpass_query.ql`.
- `seed_inputs/study_area.geojson`: missing -> DEC-004 box (unverified).
- `seed_inputs/projects/projects.geojson`: missing -> approximate geometry, invented status dates.
- `seed_inputs/zones/zone_types.json`: missing -> 8-zone placeholder list (DEC-005 wants the map legend).
- `B_INR_PER_SQM` in `gen/params.py`: PLACEHOLDER prices, replace with cited Warangal per-sq-yd ranges.
- Mandals (k-means groups) and the single district stay fallbacks for the MVP (owner decision).
- Corpus PDFs and the land-use map JPG are not in the repo yet; OQ-36 (OCR) is open.

## Known issues
- **Tile size**: a dense z14 parcel tile is ~574 KB, 454 ms cold vs the 200 ms warm p95 target (SM-3).
  `tiles_parcels` is spec 2.8 verbatim; per-zoom simplification (spec 2.18) is M6 work.
- **Root-owned CSVs**: `bench/results/*.csv` are written by the container as root; `sudo chown` to edit.
- **Q8 untested**: the runner's Q8 path (keyword/vector/hybrid variants, recall@10) has never run, because
  `document_chunk` is empty until M5 ingestion.
- Q6 at SF5 does not use I5 on page 1 (188k of 497k rows match; seq scan + top-N is cheaper); keyset uses it.
- Q2 GiST helps little: ring-road bounding boxes span the core. Q9 trigram unused on 185 villages.
- The api and CLI still connect as `landlens_owner`; switch the API server to `landlens_api` in M3.
- `harness/` and `registry/` are frozen since direct building started; their task statuses are stale.

## Next: M3
DB pool and error middleware, auth (argon2id, JWT cookie, rate limits), search/parcels, screener, trends,
valuation service + report endpoint, credits unlock transaction, 1,000-request concurrency test.
