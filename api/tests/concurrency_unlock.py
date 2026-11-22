"""Unlock load test (spec 2.11, DEC-003 OQ-08): a user with 10 credits fires 1,000 parallel unlocks on distinct
parcels against the running stack (through Caddy, 2 uvicorn workers, a pool of 10 each).

Pass means:
- exactly 10 responses are 200 with charged = 1;
- every other response is 402 insufficient_credits, or 503 with Retry-After (pool saturated), never a charge;
- in the database: 10 report_unlock rows, 10 report_unlock ledger rows on 10 distinct parcels, balance 0, and
  credit_balance = SUM(ledger.delta);
- replaying the 10 winning requests with their Idempotency-Keys charges 0 and changes nothing.

The user is created through POST /auth/signup (3 credits, signup_bonus); the other 7 are added as a top_up
ledger row plus the matching balance update in one owner transaction, as the demo account does (OQ-24), so the
ledger reconciles. Run: `make concurrency`. Writes bench/results/concurrency_unlock.json.
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import psycopg

BASE = os.environ.get("API_BASE", "http://caddy").rstrip("/")
N, CREDITS = 1000, 10
OUT = Path(os.environ.get("RESULTS_DIR", "/bench/results")) / "concurrency_unlock.json"


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


async def main() -> int:
    email = f"loadtest-{uuid.uuid4().hex[:10]}@landlens.local"
    async with httpx.AsyncClient(base_url=BASE, timeout=120,
                                 limits=httpx.Limits(max_connections=N, max_keepalive_connections=N)) as c:
        r = await c.post("/api/auth/signup", json={"email": email, "password": "loadtest-password-123"})
        r.raise_for_status()
        user_id = r.json()["user_id"]
        token = r.cookies.get("landlens_session") or r.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        cookie = {"cookie": f"landlens_session={token}"}

        with owner() as conn, conn.transaction():
            conn.execute("SELECT 1 FROM app_user WHERE user_id = %s FOR UPDATE", (user_id,))
            conn.execute("INSERT INTO credit_ledger (user_id, delta, reason) VALUES (%s, %s, 'top_up')",
                         (user_id, CREDITS - 3))
            conn.execute("UPDATE app_user SET credit_balance = credit_balance + %s WHERE user_id = %s",
                         (CREDITS - 3, user_id))
        with owner() as conn:
            parcels = [r[0] for r in conn.execute("SELECT parcel_id FROM parcel ORDER BY parcel_id LIMIT %s", (N,))]
        assert len(parcels) == N, "need 1,000 distinct parcels (seed SF1 first)"
        me = (await c.get("/api/me", headers=cookie)).json()
        assert me["credit_balance"] == CREDITS, me

        keys = {p: str(uuid.uuid4()) for p in parcels}
        start = asyncio.Event()

        async def one(p):
            await start.wait()
            t0 = time.perf_counter()
            try:
                resp = await c.post(f"/api/reports/{p}/unlock", headers={**cookie, "Idempotency-Key": keys[p]})
                body = resp.json()
                return p, resp.status_code, body, resp.headers.get("retry-after"), time.perf_counter() - t0
            except httpx.HTTPError as e:
                return p, None, {"exception": repr(e)}, None, time.perf_counter() - t0

        tasks = [asyncio.create_task(one(p)) for p in parcels]
        await asyncio.sleep(0.5)                      # every request is queued before any is sent
        t0 = time.perf_counter()
        start.set()
        results = await asyncio.gather(*tasks)
        wall = time.perf_counter() - t0

        statuses = collections.Counter(s for _, s, *_ in results)
        codes = collections.Counter((s, b.get("error", {}).get("code")) for _, s, b, *_ in results if s != 200)
        winners = [(p, b) for p, s, b, *_ in results if s == 200 and b.get("charged") == 1]
        free_200 = [p for p, s, b, *_ in results if s == 200 and b.get("charged") != 1]
        bad_503 = [p for p, s, b, ra, _ in results if s == 503 and not ra]
        other = [(p, s, b) for p, s, b, *_ in results if s not in (200, 402, 503)]
        lat = sorted(d for *_, d in results)

        # replay the winners with their keys: must be charged 0
        replay = await asyncio.gather(*[c.post(f"/api/reports/{p}/unlock",
                                               headers={**cookie, "Idempotency-Key": keys[p]}) for p, _ in winners])

    with owner() as conn:
        bal, total, unlocks, ledger_unlocks, ledger_parcels, max_per_parcel = conn.execute("""
            SELECT u.credit_balance,
                   (SELECT sum(delta) FROM credit_ledger l WHERE l.user_id = u.user_id),
                   (SELECT count(*) FROM report_unlock r WHERE r.user_id = u.user_id),
                   (SELECT count(*) FROM credit_ledger l WHERE l.user_id = u.user_id AND l.reason = 'report_unlock'),
                   (SELECT count(DISTINCT parcel_id) FROM credit_ledger l
                     WHERE l.user_id = u.user_id AND l.reason = 'report_unlock'),
                   (SELECT coalesce(max(n), 0) FROM (SELECT count(*) AS n FROM credit_ledger l
                     WHERE l.user_id = u.user_id AND l.reason = 'report_unlock' GROUP BY parcel_id) s)
            FROM app_user u WHERE u.user_id = %s""", (user_id,)).fetchone()
        unlocked = {r[0] for r in conn.execute("SELECT parcel_id FROM report_unlock WHERE user_id = %s", (user_id,))}

    checks = {
        "exactly_10_charged_200s": len(winners) == CREDITS,
        "no_uncharged_200s": not free_200,
        "others_are_402_or_503": statuses[200] + statuses[402] + statuses[503] == N and not other,
        "every_503_has_retry_after": not bad_503,
        "db_10_report_unlocks": unlocks == CREDITS,
        "db_10_ledger_unlocks_on_10_parcels": ledger_unlocks == CREDITS and ledger_parcels == CREDITS,
        "no_parcel_charged_twice": max_per_parcel <= 1,
        "winners_match_unlock_rows": unlocked == {p for p, _ in winners},
        "balance_zero": bal == 0,
        "balance_equals_ledger_sum": bal == total,
        "replays_charge_0": all(r.status_code == 200 and r.json()["charged"] == 0 for r in replay),
    }
    report = {
        "requests": N, "credits": CREDITS, "base": BASE, "wall_s": round(wall, 3),
        "statuses": {str(k): v for k, v in sorted(statuses.items(), key=lambda kv: str(kv[0]))},
        "error_codes": {f"{s}:{c}": n for (s, c), n in codes.items()},
        "latency_ms": {"p50": round(1000 * lat[len(lat) // 2], 1), "p95": round(1000 * lat[int(0.95 * len(lat))], 1),
                       "max": round(1000 * lat[-1], 1)},
        "db": {"credit_balance": bal, "ledger_sum": total, "report_unlock_rows": unlocks,
               "ledger_unlock_rows": ledger_unlocks, "ledger_unlock_parcels": ledger_parcels},
        "winning_balances": sorted(b["credit_balance"] for _, b in winners),
        "checks": checks, "pass": all(checks.values()),
    }
    print(json.dumps(report, indent=2))
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {OUT}")
    except OSError as e:
        print(f"could not write {OUT}: {e}", file=sys.stderr)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
