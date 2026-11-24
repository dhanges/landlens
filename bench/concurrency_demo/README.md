# Live two-terminal concurrency demo (spec 2.11)

The scripted version is `make demo-concurrency` (writes `bench/results/concurrency_demo.txt`). To record it live,
open two terminals side by side (e.g. tmux) and in each run:

    docker compose exec db psql -U landlens_owner -d landlens_owner

Create a demo user in either terminal first and note its id:

    INSERT INTO app_user (email, password_hash, credit_balance) VALUES ('live-demo@landlens.local', 'x', 5) RETURNING user_id;
    \set u <that id>

Type the steps in the order shown (A = left terminal, B = right). Reset with
`UPDATE app_user SET credit_balance = 5 WHERE user_id = :u;` between versions.

## 1. Broken (lost update)
    A: BEGIN; SELECT credit_balance FROM app_user WHERE user_id = :u;          -- 5
    B: BEGIN; SELECT credit_balance FROM app_user WHERE user_id = :u;          -- 5
    A: UPDATE app_user SET credit_balance = 4 WHERE user_id = :u; COMMIT;      -- app wrote read_value - 1
    B: UPDATE app_user SET credit_balance = 4 WHERE user_id = :u; COMMIT;      -- same: one purchase is lost
    A: SELECT credit_balance FROM app_user WHERE user_id = :u;                 -- 4, should be 3

## 2. Row lock (the real purchase transaction)
    A: BEGIN; SELECT credit_balance FROM app_user WHERE user_id = :u FOR UPDATE;   -- 5, row locked
    B: BEGIN; SELECT credit_balance FROM app_user WHERE user_id = :u FOR UPDATE;   -- hangs
    A: UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = :u; COMMIT;
    B:                                                                          -- returns 4 now
    B: UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = :u; COMMIT;   -- 3

## 3. SERIALIZABLE (40001 + retry)
    A: BEGIN ISOLATION LEVEL SERIALIZABLE; SELECT credit_balance FROM app_user WHERE user_id = :u;   -- 5
    B: BEGIN ISOLATION LEVEL SERIALIZABLE; SELECT credit_balance FROM app_user WHERE user_id = :u;   -- 5
    A: UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = :u; COMMIT;
    B: UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = :u;
       -- ERROR: could not serialize access due to concurrent update (SQLSTATE 40001)
    B: ROLLBACK;  -- the API retries (up to 3 times with jitter): run B's transaction again -> 3
