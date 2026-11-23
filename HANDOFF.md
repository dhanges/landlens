# LandLens handoff (M0-M5, 2026-11-23)

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
- **M4** Next.js frontend in `web/` matching `web/DESIGN.md` + `web/design/` mockups: tokens (light/dark CSS
  variables -> Tailwind + shadcn aliases), next/font, logo, no-flash theme toggle; pages `/` (landing), `/map`
  (screener + MapLibre + results), `/parcels/[id]` (locked preview, unlock, full report, print), `/trends`,
  `/pricing` (mock top-up), `/account` (ledger), `/login`, `/signup`; loading/empty/error states everywhere.
  Migration 014 slims tiles (densest z14 574 KB -> 142 KB; `bench/results/tile_weight_sf1.csv`).
  Screenshots: `report/screenshots/m4/`.
- **M5 step 0 (data realism)** fallback projects: ORR and NH-163 completed, IRR proposed; active = airport +
  textile park; project decay 1.5-4 km; per-village growth offsets. SF1 re-seeded and re-benchmarked.
- **M5** RAG: `landlens ingest-pdf` (PyMuPDF, ~400-token chunks, flags pages without text, embeddings dump in
  `seed_inputs/docs/embeddings/`, idempotent by sha256, `seed` restores from dumps), `POST /api/chat` (one hybrid
  RRF statement, not-found rule, citation check, degraded keyword-only mode, 20/min), `GET /api/documents/{id}/file`,
  chat panel on the report + `/chat` page, Q8 rotating benchmark, 25 draft eval questions + `bench/rag_eval.py`.
  **Not yet run with a key**: the corpus is not embedded (0 documents in the DB), Q8 rows are not in sf1.csv,
  the eval has not run.

## How to run (from landlens/, with your .env)
```
make up            # build, start; one-shot `migrate` service runs the schema phase (~45 s)
make seed SF=1     # schema -> gen -> post-load (010-012) -> refresh -> verify; restarts martin (~2 min)
make verify        # M1 checks
make bench         # Q1-Q9 at the main DB's SF (~5 min at SF1); subset: make bench Q="Q2 Q6"
make seed-sf5 && make bench-sf5   # second database landlens_sf5 (~10 min + ~30 min)
make test          # pytest in its own landlens_test database (~15 s; builds the test image); T="-k credits"
make concurrency   # 1,000 parallel unlocks against the running stack via Caddy (~15 s; needs make seed)
make ingest-dry    # free: parse + chunk the corpus, flagged pages, token count and cost (~$0.001)
make ingest        # PAID (OPENAI_API_KEY in .env): embed + insert + write the dump; re-running is a no-op
make bench Q=Q8    # free once ingested: Q8 latency + HNSW recall into bench/results/sf1.csv
make eval          # PAID (~$0.013 with gpt-4o-mini): 25 questions -> bench/results/rag_eval.json; EVAL_ARGS="--dry-run"
docker compose up -d --build --no-deps --wait web   # after changing web code (production build, ~2 min)
cd web && LANDLENS_DEV_PROXY=http://localhost npm run dev -- -p 3001   # hot reload; /api and /tiles via Caddy
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
| Tiles (014, post-load): parcels carry only `h` (heat class vs village median, +-10%); z14 merged into one MultiPolygon per class (half-pixel simplification, extent 1024); z15+ one feature per parcel with `parcel_id` as feature id; villages get `h` (tercile) | b6407ac |
| API additions for the UI: lat/lon on search hits, summary outline/zone name/nearest project/price_vs_median, screener `max_price_vs_median_pct` filter + survey/lat/lon per row, comparables' survey/village, projects' `announced_on` | 0ff1caa |
| `GET /auth/session` (always 200, `{user|null}`) so signed-out pages log no 401; `/me` unchanged | e55f960 |
| `make test` builds the test image, then runs without `--build` (that flag recreated db each run) | 88e3e4f |
| Map: own style on OpenFreeMap (OpenMapTiles schema) coloured from DESIGN.md tokens rather than a recoloured copy; labels in Schibsted Grotesk via MapLibre 6 `font-faces` (woff2 in `web/public/fonts`) | 15b4d12 |
| maplibre-gl 6 worker copied to `web/public/maplibre/` at dev/build (`setWorkerUrl`) | 15b4d12 |
| Parcel outline 0.4 px at z14 growing to the DESIGN 2 px at z16 (parcels are 3-5 px wide at z14) | 15b4d12 |
| Screener slider bounds from `/screener/options` ranges; panel edits are pending until "Show N parcels" (live count) | 51e4dc1 |
| Map clicks go through `/parcels/at`; screener results drawn as dots at centroids | 51e4dc1 |
| `[fallback] ` name prefixes stripped in the UI; data stays tagged, UI shows Sample data / Synthetic badges | 51e4dc1 |
| Report: valuation first (mockup order); agricultural parcels show Soil and water first (OQ-22). Header actions: Locality trends + Print to PDF (watchlist not built); optional asking-price marker; comparables add an Adjusted column | f3e828e |
| Pricing: 5 / 20 / 50 packs (DEC-004); landing shows Free, 5, 20 as in the mockup | 4b9ae0a |
| Fallback project statuses (ORR, NH-163 completed; IRR proposed); PROJECT_EFFECT tau 1.5-4 km; VILLAGE_GROWTH_SD 3.5 pp | 887159f |
| Corpus differs from DEC-005: no G.O.Ms.No.202 (not supplied); added Bhu Bharati Act 2025, AP Agri Land Conversion Act 2006, LRS 2020 FAQs; metadata in `seed_inputs/docs/manifest.json` | 082f20a |
| OpenAI via REST (httpx), not the SDK; tokens estimated as chars/4 (no tiktoken download); LLM_MODEL default gpt-4o-mini | 082f20a |
| Embeddings dump per document (DEC-006); `seed` restores documents from dumps for free (seed truncates documents) | 082f20a |
| `make ingest` / `make eval` run in the `bench` service (host UID, seed_inputs writable, OPENAI_API_KEY + LLM_MODEL from .env) | 082f20a |
| Degraded mode reuses the hybrid statement keyword-only with OR-ed terms (websearch AND finds little for questions) | 616fe60 |
| /chat response always has `answer` (null when none) and `note` | 616fe60 |
| Q8 query vectors = sampled chunk embeddings (free); per-method quality from the eval run; `hybrid_api_statement` variant | 2e0b47e |

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
- **Tile size** (fixed in 014): densest SF1 tiles 142 KB (z14) / 134 KB (z15) raw, 23 ms warm; cold z14 is still
  ~0.45 s (the merge step), the target is warm p95. SF5 tiles not measured.
- **JWT_SECRET is shorter than 32 bytes**: PyJWT logs InsecureKeyLengthWarning in the api container. Put a
  longer random value in `.env` (e.g. `openssl rand -hex 32`); not changed here (.env is off limits).
- **Unlock throughput**: 1,000 parallel unlocks take ~10 s (p50 5.9 s). 1,000 lock-free `GET /api/me` take
  5.6 s on this setup even without Caddy, so the ceiling is general request throughput (2 workers, one
  httpx client process), and the row lock adds about 2x. No latency target exists for unlocks.
- **OQ-25 done**: on http://localhost (Caddy and the dev server) Chromium 1.65 / Firefox 159 store and send the
  Secure + HttpOnly + SameSite=Lax cookie; COOKIE_SECURE stays true.
- **db recreation explained and fixed**: `docker compose run --build test` recreated db every time (88e3e4f).
- **M4 journeys** (Chromium + Firefox, light + dark, production build via Caddy): J1, J2, J4, J5 pass with no
  console errors. J3 works in degraded (keyword-only) mode until the corpus is embedded with a key.
  After the M5 data change, J1's filters narrow: peri-urban 33,295 -> within 3 km 9,088 -> >= 15 %/yr 4,951.
- Clicking the map where there is no parcel returns a 404 from `/parcels/at`, which browsers log as a console
  error (the card shows the reason). Responsive layout below 900 px is coded but not walked.
- Agricultural parcels (146) sit mostly in one village, so their cagr_5y p10-p75 is one value (-5.8 %).
- Bhu Bharati Act 2025 is a phone scan with a noisy OCR layer ("Larnd", "aippoint"); keyword hits there are
  weaker. AP Act 2006 pages 7-12 have no text (amendments): skipped, not OCR'd (OQ-36 open for them).
- `KUDAMasterPlan2041.jpg` sits in `seed_inputs/docs/`; the README expects `seed_inputs/` (not moved).
- The report's chat card was not walked in the browser (the unlock step was blocked in this session); same
  component as /chat, which was.
- Landing "See a sample report" opens parcel 1's locked preview; the landing parcel card is static sample data.
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

## Next
Owner: review `bench/rag_eval_questions.json`, set OPENAI_API_KEY (and LLM_MODEL) in .env, `make ingest`,
`make bench Q=Q8`, `make eval`; tune CHAT_MAX_DISTANCE on the eval if refusals or misses are off.
Then M6: journeys on a clean seed, final benchmarks (SF5 re-run incl. the M2/M5 variants), the three-version
concurrency demo (spec 2.11), backup/restore drill. Watchlist stays a stretch.
