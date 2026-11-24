#!/usr/bin/env bash
# Security smoke test of the running stack through Caddy (SECURITY.md). Usage: make security-check
# Exits non-zero if any check fails. Read-only except one failed login attempt.
set -uo pipefail
cd "$(dirname "$0")/.."
BASE="${BASE:-http://localhost}"
FAIL=0
pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAIL=1; }
has() { grep -qi "$2" <<<"$1" && pass "$3" || fail "$3"; }
hasnt() { grep -qi "$2" <<<"$1" && fail "$3" || pass "$3"; }

echo "security check against $BASE"
H=$(curl -s -D - -o /dev/null "$BASE/")
has "$H" "^content-security-policy: .*default-src 'self'" "page CSP (default-src 'self')"
has "$H" "^content-security-policy: .*frame-ancestors 'none'" "page CSP forbids framing"
hasnt "$H" "^content-security-policy: .*unsafe-eval" "page CSP has no unsafe-eval"
has "$H" "^x-content-type-options: nosniff" "X-Content-Type-Options: nosniff"
has "$H" "^x-frame-options: deny" "X-Frame-Options: DENY"
has "$H" "^referrer-policy: strict-origin-when-cross-origin" "Referrer-Policy"
has "$H" "^permissions-policy: camera=()" "Permissions-Policy"
has "$H" "^cross-origin-opener-policy: same-origin" "Cross-Origin-Opener-Policy"
hasnt "$H" "^server:" "no Server header on pages"
hasnt "$H" "^x-powered-by:" "no X-Powered-By header"

A=$(curl -s -D - -o /dev/null "$BASE/api/health")
has "$A" "^content-security-policy: default-src 'none'" "API JSON CSP default-src 'none'"
hasnt "$A" "^server:" "no Server header on the API (uvicorn hidden)"
D=$(curl -s -D - -o /dev/null "$BASE/api/docs")
has "$D" "^content-security-policy: .*cdn.jsdelivr.net" "Swagger UI CSP allows its CDN only"

code=$(head -c 100000 /dev/zero | tr '\0' 'a' | curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" \
  -H 'content-type: application/json' --data-binary @-)
[ "$code" = "413" ] && pass "100 KB request body rejected (413)" || fail "100 KB request body rejected (got $code)"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H 'content-type: application/json' \
  -H 'origin: https://evil.example' -d '{"email":"a@b.co","password":"x"}')
[ "$code" = "403" ] && pass "cross-site POST rejected (403)" || fail "cross-site POST rejected (got $code)"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/tiles/tiles_parcels/14/11814/7360")
[ "$code" = "405" ] && pass "tiles are GET-only (405 on POST)" || fail "tiles are GET-only (got $code)"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/documents/1/..%2F..%2F..%2Fetc%2Fpasswd")
[ "$code" != "200" ] && pass "path traversal on documents refused ($code)" || fail "path traversal on documents"

for svc in db api web martin; do
  b=$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$(docker compose ps -q "$svc")" 2>/dev/null)
  [ "$b" = "{}" ] || [ "$b" = "null" ] && pass "$svc publishes no host port" || fail "$svc publishes a host port: $b"
done
b=$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$(docker compose ps -q caddy)" 2>/dev/null)
grep -q '"80/tcp"' <<<"$b" && pass "only Caddy publishes a port (80)" || fail "Caddy port bindings: $b"
for svc in api web; do
  u=$(docker compose exec -T "$svc" id -u 2>/dev/null)
  [ -n "$u" ] && [ "$u" != "0" ] && pass "$svc container runs as non-root (uid $u)" || fail "$svc container runs as non-root (uid ${u:-?})"
done
git ls-files | grep -qE '(^|/)\.env$' && fail ".env is not tracked by git" || pass ".env is not tracked by git"

[ "$FAIL" = 0 ] && echo "security check OK" || { echo "security check FAILED"; exit 1; }
