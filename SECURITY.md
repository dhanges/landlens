# LandLens security

Scope: the Docker Compose stack (Caddy, Next.js, FastAPI, Martin, PostgreSQL) as shipped for the MVP. Checks:
`make security-check` (headers, limits, guards, ports, non-root containers against the running stack),
`make audit` (every pinned Python package and every npm lockfile package against OSV), `make test`
(`api/tests/test_security.py` plus the auth, credits and chat tests).

## Threats and controls

| Threat | Control | Where |
| --- | --- | --- |
| Network exposure | Only Caddy publishes a port (80); db, api, web, Martin are on the internal Compose network | `docker-compose.yml`, security-check |
| SQL injection | Parameterized SQL only; screener filters map to whitelisted fragments; unknown filter keys -> 422 | `routers/screener.py`, test_security |
| XSS | React escapes output; chat answers render as text with `[n]` turned into links to `/api/documents/{id}/file#page=N` only; page CSP: `default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, no `unsafe-eval` | `Caddyfile`, `chat-panel.tsx` |
| Clickjacking | `X-Frame-Options: DENY` and `frame-ancestors 'none'` on every response | `Caddyfile` |
| CSRF | Session cookie `SameSite=Lax`, `HttpOnly`, `Secure`; state changes need a JSON body (text/plain and form bodies -> 422) or a custom header (Idempotency-Key), which forces a CORS preflight the API never answers; plus a guard that rejects unsafe methods with `Sec-Fetch-Site: cross-site` or a foreign `Origin` (403 `cross_site_request`) | `app/csrf.py`, test_security |
| Credential attacks | argon2id hashes; login timing does not reveal unknown emails; 10 auth requests per minute per IP and per email; passwords >= 10 characters | `security.py`, `routers/auth.py` |
| Session theft / forgery | HS256 JWT, 24 h expiry, `exp` and `sub` required, `alg` pinned; the API warns if `JWT_SECRET` is under 32 bytes | `security.py`, `config.py` |
| Double spending / race conditions | Row lock + primary key + unique Idempotency-Key on unlocks (1,000-request test: exactly 10 charges) | `routers/credits.py`, `make concurrency`, `make demo-concurrency` |
| Path traversal | Document files resolved under `seed_inputs/` only; anything outside -> 404 | `routers/chat.py`, test_chat |
| Open redirect | Post-login `?next=` accepts same-site paths only | `auth-form.tsx` |
| Abuse / cost (LLM) | `/chat` needs a session and is limited to 20 per minute per IP and per user; question <= 500 characters; not-found rule skips the LLM | `routers/chat.py` |
| Prompt injection | Curated corpus; the model may answer only from numbered excerpts and every citation is checked | `services/rag.py` |
| Slow clients / large bodies | Caddy: header read 10 s, body read 30 s, header size 32 KB, request bodies 64 KB (413 above) | `Caddyfile`, security-check |
| Information leaks | No `Server` / `X-Powered-By` headers; unexpected errors return a generic 500 in the shared error shape | `Caddyfile`, `errors.py` |
| Database privilege | API connects as `landlens_api` (no DDL); Martin as `landlens_tiles` (tile functions and their tables only, never users or the ledger) | `013_roles.sql` |
| Container escape impact | api runs as uid 10001, web as `node` (uid 1000) | `Dockerfile`s, security-check |
| Vulnerable dependencies | Exact pins; OSV audit of all Python pins and npm lockfile packages (0 known on 2026-11-24) | `make audit` |
| Secrets | `.env` is git-ignored and excluded from the zip; `.env.example` ships | `.gitignore` |
| Data minimisation | Only email + password hash per user; no owner names or personal data in land records | spec 2.15 |
| Third-party requests | Browser talks to the app and OpenFreeMap (map tiles) only; fonts are self-hosted | page CSP `connect-src` |
| Recovery | `make backup` (pg_dump -Fc) and `make restore` (drill into a fresh container, compared with live) | `scripts/restore_drill.sh` |

## Residual risks (accepted for the MVP, planned for V1)

- **No HTTPS locally.** The stack runs on `http://localhost`, which browsers treat as a secure context, so the
  Secure cookie works. Hosted, Caddy must serve HTTPS with HSTS (block below); never expose port 80 alone.
- **`script-src 'unsafe-inline'`.** Next.js inlines its bootstrap scripts; a nonce-based CSP needs dynamic
  rendering of every page (V1). `unsafe-eval` is not allowed.
- **Rate limits are in memory, per worker** (2 workers -> up to 2x the limit) and per IP; there is no global
  request limit or DDoS protection. Hosted: put the VPS behind a CDN/WAF or add a rate-limit module to Caddy.
- **JWTs cannot be revoked** before expiry (24 h); logout only clears the cookie. V1: a token version per user.
- **Swagger UI is public** at `/api/docs` (useful for grading). Set `API_DOCS=false` when hosting.
- **The owner's `JWT_SECRET` is currently under 32 bytes** (the API logs a warning). Replace it in `.env` with
  `openssl rand -hex 32`; existing sessions end.
- Signup answers `409 email_taken`, which reveals that an email is registered (a common trade-off for UX).

## Hosted Caddyfile (V1)

Replace `:80 {` with the domain; Caddy obtains and renews certificates and redirects HTTP to HTTPS:

    landlens.example.com {
        import security_headers
        header Strict-Transport-Security "max-age=31536000; includeSubDomains"
        ...   # the same handle blocks as in Caddyfile
    }

and set `COOKIE_SECURE=true` (default), `API_DOCS=false`, a 32+ byte `JWT_SECRET` and strong database passwords.
