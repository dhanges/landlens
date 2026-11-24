"""Three-version concurrency demo for the report (spec 2.11). Two real sessions, A and B, interleaved step by step.

1. broken        READ COMMITTED, no lock: both read the balance, both write read_value - 1 -> a lost update.
2. row_lock      the purchase transaction of spec 2.11 (SELECT ... FOR UPDATE, report_unlock, ledger, balance):
                 B waits for A's lock, then sees A's new balance; balance = SUM(ledger.delta).
3. serializable  no explicit lock, SERIALIZABLE: B's write fails with SQLSTATE 40001 and the retry loop (the same
                 policy as the API: up to 3 attempts with jitter, app/db.py) succeeds on attempt 2.

Each version starts a fresh demo user with 5 credits. Run: `make demo-concurrency` (no OpenAI, no API; owner
connection). Writes bench/results/concurrency_demo.txt (two-column transcript) and concurrency_demo.json.
For a live recording in two terminals, use the psql scripts in bench/concurrency_demo/ (README there).
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
import uuid
from pathlib import Path

import psycopg
from psycopg import errors as pgerr

from landlens.db import conninfo

OUT = Path(__file__).resolve().parent / "results"
T0 = time.perf_counter()
LINES: list[str] = []


def log(session: str, text: str) -> None:
    t = time.perf_counter() - T0
    left, right = (text, "") if session == "A" else ("", text)
    line = f"{t:6.2f}s  {left:<52} | {right}"
    LINES.append(line)
    print(line, flush=True)


def note(text: str) -> None:
    LINES.append(f"         -- {text}")
    print(f"         -- {text}", flush=True)


def connect() -> psycopg.Connection:
    return psycopg.connect(conninfo(), autocommit=True)


def new_user(admin, credits: int = 5) -> int:
    uid = admin.execute(
        "INSERT INTO app_user (email, password_hash, credit_balance) VALUES (%s, 'demo-not-a-login', %s) RETURNING user_id",
        (f"concurrency-demo-{uuid.uuid4().hex[:8]}@landlens.local", credits)).fetchone()[0]
    admin.execute("INSERT INTO credit_ledger (user_id, delta, reason) VALUES (%s, %s, 'signup_bonus')", (uid, credits))
    return uid


def balance(admin, uid: int) -> tuple[int, int]:
    return admin.execute("SELECT credit_balance, (SELECT sum(delta) FROM credit_ledger WHERE user_id = %s) "
                         "FROM app_user WHERE user_id = %s", (uid, uid)).fetchone()


def broken(admin) -> dict:
    note("VERSION 1 - broken: READ COMMITTED, read then write read_value - 1, no lock")
    uid = new_user(admin)
    a, b = connect(), connect()
    a.execute("BEGIN"); log("A", "BEGIN")
    va = a.execute("SELECT credit_balance FROM app_user WHERE user_id = %s", (uid,)).fetchone()[0]
    log("A", f"SELECT credit_balance -> {va}")
    b.execute("BEGIN"); log("B", "BEGIN")
    vb = b.execute("SELECT credit_balance FROM app_user WHERE user_id = %s", (uid,)).fetchone()[0]
    log("B", f"SELECT credit_balance -> {vb}")
    a.execute("UPDATE app_user SET credit_balance = %s WHERE user_id = %s", (va - 1, uid))
    log("A", f"UPDATE SET credit_balance = {va - 1}")
    a.execute("COMMIT"); log("A", "COMMIT")
    b.execute("UPDATE app_user SET credit_balance = %s WHERE user_id = %s", (vb - 1, uid))
    log("B", f"UPDATE SET credit_balance = {vb - 1}  (no wait)")
    b.execute("COMMIT"); log("B", "COMMIT")
    final = balance(admin, uid)[0]
    note(f"two purchases from 5 credits should leave 3; the balance is {final} -> LOST UPDATE")
    a.close(); b.close()
    return {"start": 5, "purchases": 2, "final_balance": final, "expected": 3, "lost_update": final != 3}


PURCHASE_LOCK = "SELECT credit_balance FROM app_user WHERE user_id = %s FOR UPDATE"


def purchase_rest(conn, uid: int, parcel: int) -> int:
    conn.execute("INSERT INTO report_unlock (user_id, parcel_id, credits_spent) VALUES (%s, %s, 1)", (uid, parcel))
    conn.execute("INSERT INTO credit_ledger (user_id, delta, reason, parcel_id, idempotency_key) "
                 "VALUES (%s, -1, 'report_unlock', %s, %s)", (uid, parcel, uuid.uuid4()))
    return conn.execute("UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = %s "
                        "RETURNING credit_balance", (uid,)).fetchone()[0]


def row_lock(admin) -> dict:
    note("VERSION 2 - row lock: the spec 2.11 purchase transaction (SELECT ... FOR UPDATE)")
    uid = new_user(admin)
    p1, p2 = [r[0] for r in admin.execute("SELECT parcel_id FROM parcel ORDER BY parcel_id LIMIT 2")]
    a, b = connect(), connect()
    a.execute("BEGIN"); log("A", "BEGIN")
    va = a.execute(PURCHASE_LOCK, (uid,)).fetchone()[0]
    log("A", f"SELECT ... FOR UPDATE -> {va}  (row locked)")
    res = {}

    def session_b():
        b.execute("BEGIN"); log("B", "BEGIN")
        log("B", "SELECT ... FOR UPDATE  (waits for A's lock)")
        t = time.perf_counter()
        vb = b.execute(PURCHASE_LOCK, (uid,)).fetchone()[0]
        res["waited_s"] = round(time.perf_counter() - t, 2)
        res["b_saw"] = vb
        log("B", f"... got the lock after {res['waited_s']} s -> {vb}")
        nb = purchase_rest(b, uid, p2)
        log("B", f"INSERT unlock + ledger; UPDATE -> {nb}")
        b.execute("COMMIT"); log("B", "COMMIT")

    tb = threading.Thread(target=session_b)
    tb.start()
    time.sleep(1.5)                                 # B is now blocked on the row lock
    na = purchase_rest(a, uid, p1)
    log("A", f"INSERT unlock + ledger; UPDATE -> {na}")
    a.execute("COMMIT"); log("A", "COMMIT  (releases the lock)")
    tb.join()
    final, ledger = balance(admin, uid)
    note(f"B waited {res['waited_s']} s and saw {res['b_saw']} (A's committed value); balance {final}, "
         f"ledger sum {ledger} -> CORRECT")
    a.close(); b.close()
    return {"start": 5, "purchases": 2, "final_balance": final, "ledger_sum": ledger, "expected": 3,
            "b_waited_s": res["waited_s"], "b_saw": res["b_saw"], "correct": final == 3 == ledger}


def serializable(admin) -> dict:
    note("VERSION 3 - SERIALIZABLE, no explicit lock; 40001 is retried (up to 3 attempts, jitter), as the API does")
    uid = new_user(admin)
    a, b = connect(), connect()
    a.execute("BEGIN ISOLATION LEVEL SERIALIZABLE"); log("A", "BEGIN ISOLATION LEVEL SERIALIZABLE")
    va = a.execute("SELECT credit_balance FROM app_user WHERE user_id = %s", (uid,)).fetchone()[0]
    log("A", f"SELECT credit_balance -> {va}")
    b.execute("BEGIN ISOLATION LEVEL SERIALIZABLE"); log("B", "BEGIN ISOLATION LEVEL SERIALIZABLE")
    vb = b.execute("SELECT credit_balance FROM app_user WHERE user_id = %s", (uid,)).fetchone()[0]
    log("B", f"SELECT credit_balance -> {vb}")
    a.execute("UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = %s", (uid,))
    log("A", "UPDATE SET credit_balance = credit_balance - 1")
    a.execute("COMMIT"); log("A", "COMMIT")
    attempts, sqlstate = 1, None
    try:
        b.execute("UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = %s", (uid,))
        b.execute("COMMIT")
    except pgerr.SerializationFailure as e:
        sqlstate = e.sqlstate
        log("B", f"UPDATE -> ERROR {e.sqlstate}: {str(e).splitlines()[0][:40]}")
        b.execute("ROLLBACK"); log("B", "ROLLBACK")
        while attempts < 3:
            attempts += 1
            time.sleep(random.uniform(0.05, 0.2))   # jitter
            try:
                b.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
                log("B", f"retry {attempts}: BEGIN SERIALIZABLE")
                vb = b.execute("SELECT credit_balance FROM app_user WHERE user_id = %s", (uid,)).fetchone()[0]
                log("B", f"SELECT credit_balance -> {vb}")
                b.execute("UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = %s", (uid,))
                log("B", "UPDATE SET credit_balance = credit_balance - 1")
                b.execute("COMMIT"); log("B", "COMMIT")
                break
            except pgerr.SerializationFailure:
                b.execute("ROLLBACK")
    final = balance(admin, uid)[0]
    note(f"B failed with {sqlstate}, succeeded on attempt {attempts}; balance {final} -> CORRECT")
    a.close(); b.close()
    return {"start": 5, "purchases": 2, "final_balance": final, "expected": 3, "sqlstate": sqlstate,
            "attempts": attempts, "correct": final == 3 and sqlstate == "40001"}


def main() -> int:
    with connect() as admin:
        out = {"broken": broken(admin)}
        LINES.append("")
        out["row_lock"] = row_lock(admin)
        LINES.append("")
        out["serializable"] = serializable(admin)
    out["pass"] = out["broken"]["lost_update"] and out["row_lock"]["correct"] and out["serializable"]["correct"]
    OUT.mkdir(exist_ok=True)
    header = f"{'time':>7}  {'session A':<52} | session B\n" + "-" * 100
    (OUT / "concurrency_demo.txt").write_text(header + "\n" + "\n".join(LINES) + "\n")
    (OUT / "concurrency_demo.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
