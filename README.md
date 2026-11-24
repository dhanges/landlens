# LandLens

LandLens is independent land research for the Warangal (KUDA) region of Telangana: a map and screener over
every parcel, a parcel report with a fair-value range built from comparable sales, locality price trends, and a
document assistant that answers questions from government acts with page citations. It sells reports for
credits; it is not a marketplace. **All land data in this build is synthetic** (see "What is real").

## Prerequisites

- Docker with Docker Compose v2 (`docker compose version`), about 8 GB free disk (images ~5 GB)
- `make`
- **Port 80 free** (only Caddy publishes a port; stop any local web server first)
- Internet access while the images build (Docker base images, npm, PyPI, Google Fonts). Seeding needs no network.

## Run it

Unzip and enter the folder (from a git checkout, use the `landlens/` folder instead):

```
unzip landlens-submission.zip
cd landlens-submission
make up          # builds and starts the stack; first run creates .env with random local secrets
make seed SF=1   # generates the database: 100k parcels, ~343k sales, the documents
```

Measured on the fresh-machine test (2026-11-24, 12-core laptop): `make up` 1.9 min and `make seed SF=1`
2.7 min, with Docker base images already downloaded. On a machine without them, the first `make up` also pulls
about 2 GB of images and packages: allow 10-20 minutes depending on the connection. Then open
**http://localhost** (use `localhost`, not `127.0.0.1`: the session cookie is `Secure`, and browsers only accept
that over plain HTTP on `localhost`).

`make up` writes `.env` from `.env.example` only if `.env` does not exist; it never changes an existing one.

## Demo login

- Email `demo@landlens.local`, password `demolandlens` (10 credits). Or sign up: every new account gets 3 credits.

## Try this (5 steps)

1. **Screener** - open *Map*. In the left panel choose *Peri-urban*, drag *Distance to an active project* to
   about 3 km and *5-year growth* to 15%, press *Show N parcels*. The list narrows and the matches appear as dots.
2. **Parcel** - click a row (or zoom in and click a parcel). The card shows the village median, growth and the
   distance to an active project.
3. **Unlock** - press *Unlock full report · 1 credit*, sign in, unlock. The balance in the header drops by one and
   the report shows the valuation range with its drivers, price history, comparables, zoning, soil and water.
   *Print to PDF* prints it.
4. **Trends** - press *Locality trends* on the report (or *Trends* in the header, then search a village such as
   *Kazipet*). The chart shows the yearly median with the middle half of sales shaded and sales per year below;
   switch to *Whole mandal*.
5. **Chat** - *Ask* in the header, e.g. "What happens if I develop land without permission?". Answers cite the act
   and page; each citation opens the PDF at that page. Without an OpenAI key you get the best-matching passages
   in **keyword-only mode** instead of a written answer (see below).

Credits: *Pricing* has mock packs (no money moves); *Account* shows the ledger.

## What is real and what is synthetic

- **Real:** the four government documents in `seed_inputs/docs/` (Telangana Urban Areas (Development) Act
  1975, Telangana Bhu Bharati Act 2025, AP Agricultural Land Conversion Act 2006, LRS 2020 FAQs) and the
  OpenFreeMap / OpenStreetMap base map drawn under the data.
- **Synthetic:** villages and their boundaries, mandals, the roads and water in LandLens's own layers,
  development projects and their status histories, master plan zones, parcels, sales and prices, guideline
  rates, soil and groundwater. Names such as "Kazipet" or "Mamnoor airport" label synthetic shapes. The seeded
  generator is deterministic (same seed, same database). Real OSM inputs and real project geometry are V1.
- Every report and valuation says "Not legal or financial advice"; synthetic values carry badges.
- Sources and dates for every input: `seed_inputs/sources.md`.

## Chat and OpenAI

The documents are already embedded (`seed_inputs/docs/embeddings/`), so seeding never calls OpenAI. Written
answers need a key: put `OPENAI_API_KEY=...` (and optionally `LLM_MODEL`, default `gpt-4o-mini`) in `.env`, then
`docker compose up -d api`. Without a key, `/chat` runs in **degraded keyword mode**: it returns the passages that
best match the question, each with its document and page, and says so.

## Tests, benchmarks and demos

| Command | What it does | Time |
| --- | --- | --- |
| `make test` | 51 pytest tests on a 10-parcel fixture with hand-derived answers (own database) | ~1 min |
| `make concurrency` | 1,000 parallel report unlocks by a user with 10 credits: exactly 10 charged, ledger reconciles | ~20 s |
| `make demo-concurrency` | three-version transaction demo: lost update / row lock / SERIALIZABLE + retry | ~5 s |
| `make bench` | Q1-Q9 benchmark variants with EXPLAIN ANALYZE at SF1 -> `bench/results/sf1.csv` | ~6 min |
| `make seed-sf5 && make bench-sf5` | the same at SF5 (500k parcels, second database) | ~15 + 30 min |
| `make pgbench` | screener throughput at 8 and 32 clients | ~1 min |
| `make charts` | SVG charts from the results -> `bench/charts/` | seconds |
| `make backup` / `make restore` | `pg_dump -Fc`, then a restore drill into a fresh container compared with live | ~4 min |
| `make security-check` / `make audit` | hardening checks against the running stack / OSV dependency audit | ~10 s |
| `make er` | regenerate the ER diagram from the schema | seconds |
| `make ingest-dry` / `make ingest` / `make eval` | RAG: chunk the PDFs (free) / embed them (paid) / 25-question eval (paid) | - |

`make down` stops the stack (data kept); `docker compose down -v` also deletes the database volume.

## Where things live

| Path | Contents |
| --- | --- |
| `bench/results/` | benchmark CSVs (SF1, SF5), pgbench, tile weights, concurrency and restore-drill records, RAG eval |
| `bench/charts/` | benchmark charts (SVG) |
| `report/er-diagram.mmd` | ER diagram (Mermaid) generated from the migrations |
| `report/screenshots/` | screenshots of the main pages, light and dark |
| `SECURITY.md` | threats, controls, evidence and residual risks |
| `db/migrations/` | the schema: tables, indexes, materialized views, tile functions, roles |
| `api/` | FastAPI app (raw SQL), the `landlens` CLI (generator, ingest, bench), tests |
| `web/` | Next.js frontend; design brief in `web/DESIGN.md` |
| `seed_inputs/` | every input `make seed` needs, with `sources.md` |
| `HANDOFF.md` | build log: state, decisions outside the spec, known issues |

## Troubleshooting

- *Port 80 is in use*: stop the other server, or `sudo lsof -i :80` to find it.
- *Login does not stick*: you opened `127.0.0.1`; use `http://localhost`.
- *The base map is blank*: it loads from tiles.openfreemap.org and needs internet; LandLens's own layers still draw.
- *Start again from scratch*: `docker compose down -v && make up && make seed SF=1`.
