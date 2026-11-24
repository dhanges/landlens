# LandLens Makefile (spec 2.17). Every job runs in the api image (spec 2.2 "jobs").

COMPOSE := docker compose -f docker-compose.yml
SF ?= 1
SEED ?= 42
SF5_DB := landlens_sf5
# the bench service runs as the host user (results/*.csv not root-owned)
BENCH := UID=$(shell id -u) GID=$(shell id -g) $(COMPOSE) run --rm

.PHONY: up down seed verify migrate bench seed-sf5 bench-sf5 test concurrency ingest-dry ingest eval demo-concurrency

# Build and start the stack; the one-shot `migrate` service applies the schema phase first (spec 2.17).
up:
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

# Three-version concurrency demo (spec 2.11): broken / row lock / SERIALIZABLE, two real sessions, transcript in
# bench/results/concurrency_demo.txt. Live two-terminal version: bench/concurrency_demo/README.md
demo-concurrency:
	$(BENCH) bench python /app/bench/concurrency_demo.py

# 1,000 parallel unlocks by a 10-credit user against the running stack via Caddy (spec 2.11)
concurrency:
	$(BENCH) test python tests/concurrency_unlock.py
