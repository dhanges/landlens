# LandLens Makefile (spec 2.17). M0 provides `up`; seed, bench, test, backup and
# restore arrive in later milestones.

COMPOSE := docker compose -f docker-compose.yml

.PHONY: up

# Build images and bring the stack up, waiting until db and api are healthy.
# The four Postgres extensions are created by the db image init script
# (DEC-004/OQ-32); numbered migrations run in later milestones.
up:
	$(COMPOSE) up -d --build --wait
