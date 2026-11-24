#!/usr/bin/env sh
# First-run helper for `make up`: if .env does not exist, create it from .env.example with random throwaway
# secrets (database passwords, JWT secret). OPENAI_API_KEY stays empty, so chat runs in keyword-only mode until
# you add a key. An existing .env is never modified.
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  exit 0
fi
rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand)/" \
    -e "s/^LANDLENS_API_PASSWORD=.*/LANDLENS_API_PASSWORD=$(rand)/" \
    -e "s/^LANDLENS_TILES_PASSWORD=.*/LANDLENS_TILES_PASSWORD=$(rand)/" \
    -e "s/^JWT_SECRET=.*/JWT_SECRET=$(rand)/" \
    .env.example > .env
chmod 600 .env
echo "created .env with random local secrets (OPENAI_API_KEY empty: chat runs in keyword-only mode)"
