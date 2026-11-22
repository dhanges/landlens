# LandLens handoff (M0-M3, 2026-11-22)

Spec: `docs/` (PRD, Tech Spec, Roadmap, ADRs). Owner decisions `registry/decisions/DEC-*` override it.

## Built and working
- **M0** Compose stack: db (PostGIS 17-3.6 + pgvector 0.8.7), martin 1.16.1, api (FastAPI, `/api/health`),
  web (Next.js 15.5.29, lockfile), caddy 2.11.8 on :80. Only Caddy publishes a port.
- **M1** Migrations 001-009 + 013 (23 tables, enums, yearly sale partitions, roles, `landlens_as_of()`);
  `landlens migrate` with checksums and phases (spec 2.17); seeded generator (spec 2.12 steps 1-12); demo
  account; `landlens verify` (row counts, 0 spatial failures, 0 invalid geometries, point query, demo ledger).
- **M2** 010 indexes, 011 views + I5 (`mv_village_price_index`, `mv_parcel_metrics`, `mv_mandal_price_index`),
  012 tile functions (parcels, villages, zones, projects, infra, coverage); Q1-Q9 runner with results in
  `bench/results/sf1.csv` and `sf5.csv` (Q8 skipped until M5). M2 fix: Q2 `gist_subdivided` (ST_Subdivide
  pieces + GiST, 1.4 s vs 6.5 s) and `impact_lookup` (parcel_project_impact, 0.2 s); Q6 selective-filter
  variants (I5 1.1 ms vs 68 ms). SF1 re-run; SF5 not re-run, so sf5.csv lacks the new variants.
- **M3** FastAPI app in `api/landlens/app/`: async pool as `landlens_api` (10 per worker, 503 + Retry-After when
  exhausted), shared error shape, request-timing logs; auth (argon2id, HS256 JWT cookie, in-memory limits);
  search, `/parcels/at` (outside_coverage / outside_parcel_window / no_parcel_at_point), summary, screener,
  trends; valuation service and `/parcels/{id}/report` (402 report_locked); unlock (spec 2.11 transaction,
  Idempotency-Key required), mock top-up, ledger. 34 pytest tests on a 10-parcel fixture; concurrency harness
  passed (10 charged, 990 x 402, 0 x 503, balance 0 = ledger sum; `bench/results/concurrency_unlock.json`).

## How to run (from landlens/, with your .env)
```
make up            # build, start; one-shot `migrate` service runs the schema phase (~45 s)
make seed SF=1     # schema -> gen -> post-load (010-012) -> refresh -> verify; restarts martin (~2 min)
make verify        # M1 checks
make bench         # Q1-Q9 at the main DB's SF (~5 min at SF1); subset: make bench Q="Q2 Q6"
make seed-sf5 && make bench-sf5   # second database landlens_sf5 (~10 min + ~30 min)
make test          # pytest in its own landlens_test database (~15 s; builds the test image); T="-k credits"
make concurrency   # 1,000 parallel unlocks against the running stack via Caddy (~15 s; needs make seed)
```
After changing API code: `docker compose up -d --build --wait api` (tests mount the working tree; the server
runs the built image). API docs: `http://localhost/api/docs`.
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
| `bench` and `test` compose services (profile tools) run as `${UID}:${GID}`; CSVs written via rename | 5780324 |
| API server uses `API_DATABASE_URL` (landlens_api); the CLI in the api container keeps `DATABASE_URL` (owner) | 882d7d9 |
| Empty `JWT_SECRET` -> key derived from LANDLENS_API_PASSWORD, with a warning (so `make up` never fails) | 882d7d9 |
| numeric columns load as float in the API (JSON numbers, not strings) | 08299a0 |
| Search: pg_trgm `<%` word similarity at threshold 0.4 (per transaction), plus ILIKE | 08299a0 |
| Trends `land_type` optional (defaults to the most-sold type); guideline = rate in force on 31 Dec; mandal guideline = median of its villages' rates | 08299a0 |
| Screener: optional `order`; NULL sort values paged after all non-NULL ones (two-phase cursor); cursor bound to filters + sort by hash; `zone_code[]`-style keys accepted as aliases | 08299a0 |
| Valuation coefficients (hand-set): area elasticity -0.10, frontage +5%, active project -2%/km capped at 10 km, time = comparable's village index | b9bddac |
| Report adds `section_order`; signup returns 201 | b9bddac |
| Idempotency-Key reused for a different unlock -> 409 `idempotency_key_reused`; non-UUID -> 422 `invalid_idempotency_key`; top-up accepts an optional key | f3258cd |
| Load-test user: signup (+3) then a `top_up` +7 ledger row by owner SQL, like the demo account | 7df3ce4 |

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
- **JWT_SECRET is shorter than 32 bytes**: PyJWT logs InsecureKeyLengthWarning in the api container. Put a
  longer random value in `.env` (e.g. `openssl rand -hex 32`); not changed here (.env is off limits).
- **Unlock throughput**: 1,000 parallel unlocks take ~10 s (p50 5.9 s). 1,000 lock-free `GET /api/me` take
  5.6 s on this setup even without Caddy, so the ceiling is general request throughput (2 workers, one
  httpx client process), and the row lock adds about 2x. No latency target exists for unlocks.
- **OQ-25 browser check not done**: Secure cookie over http://localhost is untested in Chrome/Firefox (curl
  and httpx-over-https only). If login does not stick in a browser, set COOKIE_SECURE=false.
- **Unexplained db container recreation**: during one `docker compose up -d --build --wait api` (07:54 GMT)
  Compose recreated `db` (same image, volume kept, data intact); the pool reconnected on its own.
- Survey-number search without `village_id` scans `parcel` (no index on survey_no alone; ~100k rows at SF1).
- `/screener/options` is cached 5 min per worker; it goes stale after a re-seed until then.
- Watchlist (OQ-09 stretch), `/chat` and `/documents/{id}/file` (M5) are not built.
- **Q8 untested**: the runner's Q8 path (keyword/vector/hybrid variants, recall@10) has never run, because
  `document_chunk` is empty until M5 ingestion.
- Q6 at SF5 does not use I5 on page 1 (188k of 497k rows match; seq scan + top-N is cheaper); keyset uses it.
- Q2 plain GiST helps little (ring-road bounding boxes span the core); subdivided pieces fix that. The
  impact-table variant counts parcels by centroid distance: 93,303 vs 93,434 by geometry at SF1.
- Q9 trigram unused on 185 villages.
- `harness/` and `registry/` are frozen since direct building started; their task statuses are stale.

## Next: M4
Frontend: map (MapLibre + Martin sources, click-to-summary), screener, report, trends, landing, pricing.
Remaining M3-adjacent items: watchlist API (stretch), the three-version concurrency demo for the report
(broken / row lock / SERIALIZABLE, spec 2.11), the OQ-25 browser cookie check.
