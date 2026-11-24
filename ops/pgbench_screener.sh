#!/usr/bin/env bash
# pgbench on the screener (spec 2.19): 30 s at 8 and at 32 clients against the main database (or DB=landlens_sf5).
# Writes bench/results/pgbench_<db>.csv: clients, tps, latency_avg_ms, transactions.
set -euo pipefail
cd "$(dirname "$0")/.."
DB="${DB:-landlens_owner}"
SECS="${SECS:-30}"
OUT="bench/results/pgbench_${DB}.csv"
docker compose cp bench/pgbench/screener.sql db:/tmp/screener.sql
echo "clients,tps,latency_avg_ms,transactions,duration_s" > "$OUT"
for c in 8 32; do
  res=$(docker compose exec -T db pgbench -n -U landlens_owner -c "$c" -j 4 -T "$SECS" -f /tmp/screener.sql "$DB" 2>&1)
  tps=$(echo "$res" | sed -n 's/^tps = \([0-9.]*\).*/\1/p' | head -1)
  lat=$(echo "$res" | sed -n 's/^latency average = \([0-9.]*\) ms/\1/p')
  n=$(echo "$res" | sed -n 's/^number of transactions actually processed: \([0-9]*\).*/\1/p')
  echo "$c,$tps,$lat,$n,$SECS" >> "$OUT"
  echo "pgbench $DB clients=$c: tps=$tps latency_avg=${lat} ms transactions=$n"
done
echo "wrote $OUT"
