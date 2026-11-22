# LandLens Makefile (spec 2.17). Every job runs in the api image (spec 2.2 "jobs").

COMPOSE := docker compose -f docker-compose.yml
SF ?= 1
SEED ?= 42
SF5_DB := landlens_sf5

.PHONY: up down seed verify migrate bench seed-sf5 bench-sf5

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

# Q1-Q9 benchmarks (spec 2.19) on the main database; writes bench/results/sf<N>.csv
bench:
	$(COMPOSE) exec -T api landlens bench

# SF5 in a second database on the same server (spec 3.3 M2)
seed-sf5:
	$(COMPOSE) exec -T db createdb -U landlens_owner $(SF5_DB) || true
	$(COMPOSE) exec -T -e LANDLENS_DB_NAME=$(SF5_DB) api landlens seed --sf 5 --seed $(SEED)

bench-sf5:
	$(COMPOSE) exec -T -e LANDLENS_DB_NAME=$(SF5_DB) api landlens bench
