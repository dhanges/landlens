# LandLens Makefile (spec 2.17). Every job runs in the api image (spec 2.2 "jobs").

COMPOSE := docker compose -f docker-compose.yml
SF ?= 1
SEED ?= 42
SF5_DB := landlens_sf5
# the bench service runs as the host user (results/*.csv not root-owned)
BENCH := UID=$(shell id -u) GID=$(shell id -g) $(COMPOSE) run --rm

.PHONY: up down seed verify migrate bench seed-sf5 bench-sf5 test concurrency ingest-dry ingest eval demo-concurrency backup restore security-check audit pgbench charts zip er

# Build and start the stack; the one-shot `migrate` service applies the schema phase first (spec 2.17).
# First run: creates .env from .env.example with random local secrets (an existing .env is never touched).
up:
	sh scripts/make_env.sh
	$(COMPOSE) up -d --build --wait
	$(COMPOSE) logs migrate | tail -3

down:
	$(COMPOSE) down

# Schema phase, load, post-load phase, refresh, verify (spec 2.17). Example: make seed SF=1
seed:
	$(COMPOSE) exec -T api landlens seed --sf $(SF) --seed $(SEED)
	$(COMPOSE) restart martin   # Martin discovers tile functions (migration 012) at startup

verify:
	$(COMPOSE) exec -T api landlens verify

migrate:
	$(COMPOSE) exec -T api landlens migrate --phase all

# Q1-Q9 benchmarks (spec 2.19) on the main database; writes bench/results/sf<N>.csv. Subset: make bench Q="Q2 Q6"
bench:
	$(BENCH) bench landlens bench $(Q)

# SF5 in a second database on the same server (spec 3.3 M2)
seed-sf5:
	$(COMPOSE) exec -T db createdb -U landlens_owner $(SF5_DB) || true
	$(COMPOSE) exec -T -e LANDLENS_DB_NAME=$(SF5_DB) api landlens seed --sf 5 --seed $(SEED)

bench-sf5:
	$(BENCH) -e LANDLENS_DB_NAME=$(SF5_DB) bench landlens bench $(Q)

# pytest on the 10-parcel fixture (spec 2.16), in its own landlens_test database. Subset: make test T="-k credits"
test:
	$(COMPOSE) --profile tools build test
	$(BENCH) test pytest -q tests $(T)

# RAG corpus (spec 2.13). ingest-dry is free (parse + chunk + cost estimate); ingest calls OpenAI embeddings with
# OPENAI_API_KEY from .env, writes seed_inputs/docs/embeddings/<sha256>.json and inserts. Re-running is a no-op.
ingest-dry:
	$(BENCH) bench landlens ingest-pdf --dry-run

ingest:
	$(BENCH) bench landlens ingest-pdf

# 25-question eval (spec 2.13): calls /chat's pipeline with your key (paid: ~25 embeddings + up to 25 LLM calls)
eval:
	$(BENCH) bench python /app/bench/rag_eval.py $(EVAL_ARGS)

# Submission zip (spec 3.3 M7): dist/landlens-submission.zip with one top-level folder landlens-submission/.
# Excludes .env, data volumes and backups, node_modules, build output and caches; seed_inputs/ is included so a
# fresh machine seeds without downloads or an OpenAI key. Needs only make + zip (the harness runs it in Alpine);
# then runs the zip_contents check (harness/zipcheck.py) when python3 is available, and prints the size.
ZIP := dist/landlens-submission.zip
zip:
	mkdir -p dist
	rm -f $(ZIP) dist/landlens-submission
	ln -s .. dist/landlens-submission
	cd dist && zip -qr landlens-submission.zip landlens-submission \
	  -x 'landlens-submission/dist/*' 'landlens-submission/backups/*' 'landlens-submission/data/*' \
	     '*/.env' '*/.env.local' '*/.env.*.local' '*/pgdata/*' '*/wal_archive/*' \
	     '*/node_modules/*' '*/.next/*' '*/out/*' '*/__pycache__/*' '*.pyc' '*/.pytest_cache/*' '*/.ruff_cache/*' \
	     '*/.venv/*' '*/*.egg-info/*' '*.tsbuildinfo' 'landlens-submission/web/next-env.d.ts' \
	     'landlens-submission/web/public/maplibre/*' '*/.DS_Store'
	rm -f dist/landlens-submission
	@if unzip -l $(ZIP) | awk '{print $$4}' | grep -E '(^|/)\.env$$' >/dev/null; then echo "FORBIDDEN: .env in zip"; exit 1; fi
	@if command -v python3 >/dev/null 2>&1 && [ -f ../harness/zipcheck.py ]; then python3 ../harness/zipcheck.py $(ZIP); \
	  else echo "zip_contents: harness/zipcheck.py not available here; .env check above passed"; fi
	@ls -lh $(ZIP) | awk '{print "size:", $$5, "  path:", $$9}'

# ER diagram (Mermaid) from the migrated schema: report/er-diagram.mmd
er:
	python3 scripts/er_diagram.py

# Security (SECURITY.md): headers/limits/guards against the running stack; dependency audit against OSV
security-check:
	scripts/security_check.sh

audit:
	python3 scripts/audit.py

# pgbench on the screener at 8 and 32 clients (spec 2.19); DB=landlens_sf5 for SF5
pgbench:
	DB=$(or $(DB),landlens_owner) scripts/pgbench_screener.sh

# Benchmark charts (SVG) from bench/results into bench/charts
charts:
	python3 bench/charts.py

# Backup (spec 2.11): pg_dump -Fc of the main database into backups/ (git-ignored)
backup:
	mkdir -p backups
	$(COMPOSE) exec -T db pg_dump -U landlens_owner -Fc landlens_owner > backups/landlens_$$(date +%Y%m%d_%H%M%S).dump
	@ls -lh backups | tail -1

# Restore drill: the newest backup (or DUMP=path) into a fresh throwaway container, compared with the live DB
restore:
	scripts/restore_drill.sh $(DUMP)

# Three-version concurrency demo (spec 2.11): broken / row lock / SERIALIZABLE, two real sessions, transcript in
# bench/results/concurrency_demo.txt. Live two-terminal version: bench/concurrency_demo/README.md
demo-concurrency:
	$(BENCH) bench python /app/bench/concurrency_demo.py

# 1,000 parallel unlocks by a 10-credit user against the running stack via Caddy (spec 2.11)
concurrency:
	$(BENCH) test python tests/concurrency_unlock.py
