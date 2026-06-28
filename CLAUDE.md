# Security Vulnerability Lab

> **⚠️ Educational use only.** This application is deliberately vulnerable. Do
> **not** deploy it to production or expose it to the public internet. Use it
> only on systems you own or have explicit permission to test.

An intentionally vulnerable FastAPI web application for OWASP-style security
training. Eight common web flaws are present and demonstrable; the goal is to
find, exploit, and then research how to mitigate each one.

## Quick start

```bash
# 1. Install dependencies (project root)
uv sync

# 2. Run the backend
uv run backend/app/main.py
#    or, equivalently from inside backend/:
#       uv run python -m app.main

# 3. Open the app
#    http://localhost:3001
```

Override the port with `PORT=4000 uv run backend/app/main.py` if needed.

To reset the database, delete `vulnerable_app.db` from the project root and
restart — `init_db()` will recreate the schema on the next import.

## Architecture

```
.
├── backend/                    Python package, buildable with hatchling
│   ├── pyproject.toml          Backend-scoped deps + pytest (dev)
│   └── app/
│       ├── main.py             FastAPI app, SessionMiddleware, static mounts
│       ├── core/security.py    MD5 password helpers (Vuln #5)
│       ├── db/session.py       SQLite connection + init_db()
│       ├── services/
│       │   └── auth_service.py signup/login business logic (Vuln #1)
│       └── api/routes/
│           └── auth.py         All HTTP routes (Vuln #2, #3, #6)
│
└── frontend/
    ├── templates/              Plain HTML, read from disk per request
    │   ├── login.html
    │   ├── signup.html
    │   └── dashboard.html
    └── static/
        ├── css/styles.css
        └── images/             Logo PNGs (PUCIT_Logo, blue-logo-scl2)
```

### `sys.path` shim in `main.py`

`backend/app/main.py` inserts its own directory into `sys.path` at the very
top, before any `app.*` imports. This lets the file be launched as
`uv run backend/app/main.py` (from the project root) **or**
`uv run python -m app.main` (from inside `backend/`) without import errors.
Do not remove that shim.

## Vulnerability map

| # | Vulnerability | File | Mechanism |
|---|---|---|---|
| 1 | SQL Injection (login & signup) | `backend/app/services/auth_service.py` | `INSERT` / `SELECT` built with `+` concatenation |
| 2 | Stored XSS (dashboard) | `backend/app/api/routes/auth.py` (`/welcome`) | `str.replace("{{username}}", username)` with no `html.escape` |
| 3 | Reflected XSS (search) | `backend/app/api/routes/auth.py` (`/search`) | Query param `q` interpolated into `LIKE` and HTML body |
| 4 | Session hijacking | `backend/app/main.py` | Hardcoded `secret_key="super-secret-key-12345"` |
| 5 | Weak password storage | `backend/app/core/security.py` | MD5, no salt, no work factor |
| 6 | Exposed database | `backend/app/api/routes/auth.py` (`/download/db`) | `FileResponse("vulnerable_app.db")` with no auth check |
| 7 | No rate limiting | All routes | No middleware, no decorator, no backoff |
| 8 | CSRF (no tokens) | All forms | No token generation, no `SameSite` enforcement |

All eight are intentional and form the educational content of the lab. Do
**not** "fix" them — doing so defeats the purpose of the application.

## Frontend ↔ backend integration

| Flow | Mechanism |
|---|---|
| Signup | Standard HTML `<form action="/signup" method="POST">` → server returns 302 redirect to `/login` on success, or 400 HTML `"Username already exists"` on UNIQUE-constraint violation. |
| Login | JS-driven `fetch('/login', { method: 'POST', body: formData })` → server returns JSON `{success, redirect}` or `{success: false, error}`. The form's `addEventListener('submit', e => e.preventDefault())` swaps the redirect for an inline error span. |
| Logout | `GET /logout` → server clears the session and 302s to `/login`. |
| Dashboard | `GET /welcome` → server checks `request.session['user_id']`; if missing, redirects to `/login`; otherwise reads `dashboard.html` and replaces `{{username}}` server-side. |
| Search | `GET /search?q=...` → server renders a small inline HTML page. Errors include `str(e)` so tracebacks leak. |

## Specification hierarchy

1. `docs/PRD.md` — product requirements, vulnerability catalogue, user stories.
2. `docs/TDD.md` — technical design, schema, endpoint contract, default port.
3. `.claude/specs/app-foundation.md` — implementation addendum (visual design, flows, validation, acceptance criteria).
4. `.claude/specs/app-foundation-plan.md` — phase-by-phase build plan.
5. This file (`CLAUDE.md`) — orientation for the assistant.

When changing behaviour, update the spec document before the code.

## Development commands

```bash
# Run the app (dev)
uv run backend/app/main.py

# Hot-reload while iterating
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 3001
#   (run from inside `backend/`)

# Reset DB
rm -f vulnerable_app.db

# Backend tests (pytest scaffold only — no tests yet)
cd backend && uv run --extra dev pytest
```

## Notes for future contributors

- The intentional vulnerabilities are the feature. If you find yourself
  wanting to add parameterised queries, salt the password hashes, escape
  output, install CSRF middleware, or rate-limit anything — **stop and
  confirm with the spec**. The current behaviour matches the TDD by design.
- The `sys.path` shim in `main.py` is load-bearing. Removing it will break
  the `uv run backend/app/main.py` launch path.
- Frontend templates are read from disk on every request. There is no
  template engine, no caching, and no JS framework. Keep it that way
  unless the spec changes.
