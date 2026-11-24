#!/usr/bin/env bash
# Restore drill (spec 2.11 "Recovery"): restore a pg_dump -Fc file into a FRESH throwaway container built from the
# same db image, then compare it with the live database. Usage: scripts/restore_drill.sh [backups/<file>.dump]
# Writes bench/results/restore_drill.txt. Stops and deletes only its own container (landlens-restore-drill).
set -euo pipefail
cd "$(dirname "$0")/.."
DUMP="${1:-$(ls -t backups/*.dump 2>/dev/null | head -1)}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then echo "no dump found: run make backup first" >&2; exit 1; fi
IMAGE="$(docker compose images -q db | head -1)"
NAME="landlens-restore-drill"
OUT="bench/results/restore_drill.txt"
cleanup() { docker container rm --force landlens-restore-drill >/dev/null 2>&1 || true; }
cleanup
trap cleanup EXIT

echo "restore drill: $DUMP ($(du -h "$DUMP" | cut -f1)) into a fresh container from image ${IMAGE:0:12}"
docker run -d --name "$NAME" -e POSTGRES_USER=landlens_owner -e POSTGRES_PASSWORD=drill-only "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  # the image's entrypoint runs init scripts on a temporary server first; wait for the final one
  if docker logs "$NAME" 2>&1 | grep -q "PostgreSQL init process complete"; then break; fi
  sleep 1
done
until docker exec "$NAME" pg_isready -U landlens_owner -q 2>/dev/null; do sleep 1; done
# roles are cluster-level and not in the dump: create them (no login) so the dump's grants restore unchanged
docker exec "$NAME" psql -q -U landlens_owner -d postgres -c "CREATE ROLE landlens_api NOLOGIN" -c "CREATE ROLE landlens_tiles NOLOGIN"
docker exec "$NAME" psql -q -U landlens_owner -d postgres -c "DROP DATABASE IF EXISTS landlens_owner WITH (FORCE)" -c "CREATE DATABASE landlens_owner"
docker cp "$DUMP" "$NAME":/tmp/restore.dump
START=$(date +%s)
docker exec "$NAME" pg_restore -U landlens_owner -d landlens_owner --exit-on-error -j 4 /tmp/restore.dump
SECS=$(( $(date +%s) - START ))

CHECK="SELECT 'parcel', count(*)::text FROM parcel UNION ALL SELECT 'sale_transaction', count(*)::text FROM sale_transaction
UNION ALL SELECT 'app_user', count(*)::text FROM app_user UNION ALL SELECT 'credit_ledger', count(*)::text FROM credit_ledger
UNION ALL SELECT 'report_unlock', count(*)::text FROM report_unlock UNION ALL SELECT 'document_chunk', count(*)::text FROM document_chunk
UNION ALL SELECT 'mv_parcel_metrics', count(*)::text FROM mv_parcel_metrics
UNION ALL SELECT 'sum credit_balance', coalesce(sum(credit_balance), 0)::text FROM app_user
UNION ALL SELECT 'sum ledger delta', coalesce((SELECT sum(delta) FROM credit_ledger), 0)::text
UNION ALL SELECT 'sales checksum', md5(string_agg(txn_id || ':' || consideration_inr, ',' ORDER BY txn_id)) FROM sale_transaction
UNION ALL SELECT 'schema_migrations', count(*)::text FROM schema_migrations"
CHECK="SELECT * FROM ($CHECK) c(k, v) ORDER BY k"    # same row order on both sides
LIVE=$(docker compose exec -T db psql -U landlens_owner -d landlens_owner -At -F '=' -c "$CHECK")
REST=$(docker exec "$NAME" psql -U landlens_owner -d landlens_owner -At -F '=' -c "$CHECK")
{
  echo "restore drill $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "dump: $DUMP ($(du -h "$DUMP" | cut -f1)); pg_restore -j 4 into a fresh container took ${SECS} s"
  printf '%-20s %-34s %-34s %s\n' check live restored match
  paste <(echo "$LIVE") <(echo "$REST") | while IFS=$'\t' read -r l r; do
    printf '%-20s %-34s %-34s %s\n' "${l%%=*}" "${l#*=}" "${r#*=}" "$([ "$l" = "$r" ] && echo yes || echo NO)"
  done
} | tee "$OUT"
if grep -q " NO$" "$OUT"; then echo "MISMATCH" >&2; exit 1; fi
echo "restore drill OK"
