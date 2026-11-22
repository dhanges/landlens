# LandLens Makefile (spec 2.17). Every job runs in the api image (spec 2.2 "jobs").

COMPOSE := docker compose -f docker-compose.yml
SF ?= 1
SEED ?= 42

.PHONY: up down seed verify migrate

# Build and start the stack, then apply the schema-phase migrations (spec 2.17: make up runs the schema phase only).
up:
	$(COMPOSE) up -d --build --wait
	$(COMPOSE) exec -T api landlens migrate --phase schema

down:
	$(COMPOSE) down

# Schema phase, load, post-load phase, refresh, verify (spec 2.17). Example: make seed SF=1
seed:
	$(COMPOSE) exec -T api landlens seed --sf $(SF) --seed $(SEED)

verify:
	$(COMPOSE) exec -T api landlens verify

migrate:
	$(COMPOSE) exec -T api landlens migrate --phase all
