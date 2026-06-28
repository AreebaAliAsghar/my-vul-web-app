# Implementation Plan: Intentionally Vulnerable Web Application

**Project:** `my-vuln-web-app` — Security Vulnerability Lab
**Branch:** `feature/app-foundation`
**Stack:** FastAPI + Uvicorn + SQLite + Starlette Sessions + Vanilla HTML/CSS/JS

> **⚠️ Educational Use Only.** This plan deliberately reproduces the eight vulnerabilities catalogued in `docs/PRD.md` and `docs/TDD.md`. The application must NEVER be deployed to production or used against systems without explicit permission.

---

## Context

This plan translates the behavioral specification at `.claude/specs/app-foundation.md` into a concrete, ordered set of build steps. It defines the exact files to create, the contents that distinguish them, and how each phase locks down one layer of the application before the next is wired on top.

The deliverable is a self-contained FastAPI service that:
- Serves a two-page auth flow (signup → login) and a post-login dashboard.
- Persists users in SQLite with MD5-hashed, unsalted passwords.
- Exposes a public `/download/db` endpoint that returns the database file unauthenticated.
- Implements every vulnerability listed in §1 below via string-concatenated SQL, unescaped HTML, an unauthenticated file download route, and a hardcoded session secret.
- Provides no CSRF tokens and no rate limiting on any endpoint.

**Vulnerability Map (must be present and demonstrable in the final app):**

| # | Vulnerability | Location | Mechanism |
|---|---|---|---|
| 1 | SQL Injection (login & signup) | `backend/app/services/auth_service.py` | String-concatenated `INSERT` / `SELECT` |
| 2 | Stored XSS | `backend/app/api/routes/auth.py` (`/welcome`) | `{{username}}` placeholder replaced via `str.replace` and rendered unescaped |
| 3 | Reflected XSS | `backend/app/api/routes/auth.py` (`/search`) | Query parameter `q` interpolated into HTML response without escaping |
| 4 | Session Hijacking | `backend/app/main.py` | `SessionMiddleware` initialised with hardcoded `"super-secret-key-12345"` |
| 5 | Weak Password Storage | `backend/app/core/security.py` | MD5 hexdigest, no salt, no work factor |
| 6 | Exposed Database | `backend/app/api/routes/auth.py` (`/download/db`) | `FileResponse` of `vulnerable_app.db` with no session check |
| 7 | No Rate Limiting | All routes | No middleware, decorators, or backoff implemented |
| 8 | CSRF | All forms | No token generation, no token validation, no `SameSite` enforcement beyond framework defaults |

---

## Phase 1 — Project Structure

**Goal:** Lay out the backend Python package, the backend-specific `pyproject.toml`, and the frontend asset directories. Frontend logo files already exist at `frontend/static/images/`; this phase confirms they are in place and creates the empty template and CSS directories.

### Files to create

```
backend/
├── pyproject.toml
└── app/
    ├── __init__.py                  (empty)
    ├── main.py
    ├── core/
    │   ├── __init__.py              (empty)
    │   └── security.py
    ├── db/
    │   ├── __init__.py              (empty)
    │   └── session.py
    ├── services/
    │   ├── __init__.py              (empty)
    │   └── auth_service.py
    └── api/
        ├── __init__.py              (empty)
        └── routes/
            ├── __init__.py          (empty)
            └── auth.py

frontend/
├── templates/                       (will hold login.html, signup.html, dashboard.html)
└── static/
    ├── css/                         (will hold styles.css)
    └── images/                      (logo PNGs already present — verify in place)
```

### Key details

- **Two `pyproject.toml` files.** The repo-root `pyproject.toml` already declares the umbrella project (`my-vuln-web-app`, FastAPI stack). Create a **separate** `backend/pyproject.toml` for the `app` package so it can be developed/installed in isolation.
- **`backend/pyproject.toml` contents:**
  - `[build-system]` → `requires = ["hatchling"]`, `build-backend = "hatchling.build"`
  - `[project]` → `name = "app"`, `version = "0.1.0"`, `requires-python = ">=3.12"`
  - `dependencies = ["fastapi>=0.109.0", "uvicorn>=0.27.0", "python-multipart>=0.0.6", "itsdangerous>=2.0.0"]`
  - `[project.optional-dependencies] dev = ["pytest"]`
  - `[tool.hatch.build.targets.wheel] packages = ["app"]`
- **Empty `__init__.py` files** at every Python package level so `app.*` imports resolve regardless of cwd.
- **Logo files** in `frontend/static/images/` are already present — do not regenerate them.

---

## Phase 2 — Database Layer (`backend/app/db/session.py`)

**Goal:** Provide a single SQLite connection to `vulnerable_app.db` at the project root and an idempotent `init_db()` that creates the `users` table on first run.

### Implementation details

- **Connection target:** `sqlite3.connect("vulnerable_app.db")` — relative path resolved against the process cwd at module import.
- **Row factory:** `conn.row_factory = sqlite3.Row` so callers can access columns by name.
- **`check_same_thread=False`** to avoid SQLite threading complaints when FastAPI dispatches across threads.
- **Module-level `conn` singleton** — one connection reused for the lifetime of the process (matches the TDD's "single-connection" model).
- **`init_db()` function:**
  - Executes `CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, email TEXT, password TEXT)`.
  - Calls `conn.commit()` after the DDL.
  - Safe to call repeatedly (idempotent).
- **Exported symbols:** `conn`, `init_db`.

### Vulnerability tie-in

- The schema deliberately omits any password-strength / salt columns — this is the foundation that Vulnerability #5 (Weak Password Storage) builds on.
- The single shared connection with `check_same_thread=False` is acceptable here; concurrency control is intentionally absent (consistent with Vulnerability #7, No Rate Limiting).

---

## Phase 3 — Security Utilities (`backend/app/core/security.py`)

**Goal:** Provide MD5-based password hashing and verification helpers. **No salt, no work factor, no modern KDF.**

### Implementation details

- Import `hashlib`.
- **`hash_password(password: str) -> str`:**
  - `return hashlib.md5(password.encode("utf-8")).hexdigest()`
  - Returns the lowercase 32-char hex digest. No salt is added.
- **`verify_password(plain: str, hashed: str) -> str`:**
  - `return hash_password(plain) == hashed`
  - Plain comparison; no constant-time helper, no per-user salt lookup.
- The file should contain a short comment noting these are intentionally weak (so future maintainers understand the educational intent).

### Vulnerability tie-in

- This module **is** Vulnerability #5. Every signup that funnels through `hash_password()` produces a value vulnerable to rainbow-table and dictionary attacks.

---

## Phase 4 — Business Logic (`backend/app/services/auth_service.py`)

**Goal:** Implement `signup()` and `login()` against the SQLite layer using string-concatenated SQL. **Both functions are SQL-injection sinks by design (Vulnerability #1).**

### `signup(username, email, password)`

- Inputs: `username: Form`, `email: Form`, `password: Form`.
- Validate all three are non-empty; if any are blank, raise `HTTPException(400, "All fields are required")`.
- Hash the password via `hash_password()`.
- **Build the `INSERT` via string concatenation** (do **not** use parameterised queries):
  ```python
  query = (
      "INSERT INTO users (username, email, password) VALUES ('"
      + username + "', '" + email + "', '" + hashed + "')"
  )
  conn.execute(query)
  conn.commit()
  ```
- Wrap the `execute` in a `try/except sqlite3.IntegrityError`. On `IntegrityError` (UNIQUE constraint on `username`), return an `HTMLResponse` with status 400 and body `"Username already exists"`.
- On success, return `RedirectResponse(url="/login", status_code=302)`.

### `login(request, username, password)`

- Inputs: `request: Request`, `username: Form`, `password: Form`.
- Validate both are non-empty; if any are blank, return `JSONResponse({"success": False, "error": "Username and password are required"}, status_code=400)`.
- Hash the password via `hash_password()`.
- **Build the `SELECT` via string concatenation** (do **not** use parameterised queries):
  ```python
  query = (
      "SELECT * FROM users WHERE username = '"
      + username + "' AND password = '" + hashed + "'"
  )
  row = conn.execute(query).fetchone()
  ```
- If a row is returned, write `user_id`, `username`, `email` into `request.session`, then return:
  ```python
  JSONResponse({"success": True, "redirect": "/welcome"})
  ```
  The frontend JS reads `data.redirect` and uses `window.location.href = data.redirect`.
- If no row matches, return:
  ```python
  JSONResponse({"success": False, "error": "Invalid username or password"}, status_code=401)
  ```
  The frontend JS shows `data.error` inline (no page reload).

### Vulnerability tie-in

- This file is **Vulnerability #1.** Every `+` operator joining user input into the SQL string is intentional. Reviewers must be able to grep for `+ username` / `+ email` / `+ password` / `+ hashed` and see exactly the injection sinks.
- The `login` path also exposes Vulnerability #5 directly — even a perfectly written SQL query would still hand back matches for any password whose MD5 happens to match a stored one.

---

## Phase 5 — Route Handlers (`backend/app/api/routes/auth.py`)

**Goal:** Expose all user-facing endpoints on a single `APIRouter`. This file is the home of Vulnerabilities #2, #3, and #6.

### Routes

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/` | `RedirectResponse("/signup", status_code=302)` |
| `GET` | `/signup` | Read `frontend/templates/signup.html` from disk; return `HTMLResponse(content)` |
| `POST` | `/signup` | Delegate to `auth_service.signup(username, email, password)` |
| `GET` | `/login` | Read `frontend/templates/login.html` from disk; return `HTMLResponse(content)` |
| `POST` | `/login` | Delegate to `auth_service.login(request, username, password)` |
| `GET` | `/download/db` | `FileResponse("vulnerable_app.db", filename="vulnerable_app.db", media_type="application/octet-stream")` — **no session check, no auth** (Vulnerability #6) |
| `GET` | `/search` | Read query param `q`; build `SELECT … LIKE '%' + q + '%'` via concatenation; return HTMLResponse with results; `q` interpolated into HTML unescaped (Vulnerability #3); on exception, return `"Error: " + str(e)` so the traceback leaks into the response |
| `GET` | `/welcome` | If `'user_id'` not in `request.session`, redirect to `/login`. Else read `dashboard.html`, do `html.replace("{{username}}", username)`, return `HTMLResponse` (Vulnerability #2 — stored XSS) |
| `GET` | `/logout` | `request.session.clear()`; `RedirectResponse("/login", status_code=302)` |

### Key implementation details

- **Per-request template reads.** Each handler does `open(path, "r", encoding="utf-8").read()` inline. No template engine, no caching. This is documented in the spec as deliberate (matches current repo behaviour).
- **`/download/db` resolution.** Use a path relative to the project root (`vulnerable_app.db`), matching the DB connection in `db/session.py`. Because the route lives in a router module, the working directory at import time is what matters; document this in a comment.
- **`/search` query construction:**
  ```python
  q = request.query_params.get("q", "")
  sql = "SELECT username, email FROM users WHERE username LIKE '%" + q + "%'"
  rows = conn.execute(sql).fetchall()
  body = "<h2>Search results for: " + q + "</h2><ul>"
  for r in rows:
      body += "<li>" + r["username"] + " — " + r["email"] + "</li>"
  body += "</ul>"
  return HTMLResponse(body)
  ```
  Both the `LIKE` clause and the response body interpolate `q` unescaped — Vulnerability #3 surface.
- **`/welcome` template substitution:**
  ```python
  html = open("frontend/templates/dashboard.html", "r", encoding="utf-8").read()
  username = request.session.get("username", "")
  html = html.replace("{{username}}", username)
  return HTMLResponse(html)
  ```
  No `html.escape(username)` — Vulnerability #2 surface.

### Vulnerability tie-in

- `/welcome` → Vulnerability #2 (Stored XSS)
- `/search` → Vulnerability #3 (Reflected XSS) plus a bonus information-disclosure path (`str(e)` in error responses)
- `/download/db` → Vulnerability #6 (Exposed Database)
- Absence of CSRF tokens and rate limiting across all routes → Vulnerabilities #7 and #8

---

## Phase 6 — Application Entry Point (`backend/app/main.py`)

**Goal:** Wire the FastAPI app, install `SessionMiddleware` with the weak secret, mount static assets, include the auth router, initialise the DB, and run Uvicorn.

### Module header — sys.path shim

At the **very top** of `main.py`, before any `app.*` imports:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
```
This lets the file be launched either as `python backend/app/main.py` from the project root or `python app/main.py` from `backend/`.

### Imports and setup

- `from fastapi import FastAPI`
- `from fastapi.staticfiles import StaticFiles`
- `from starlette.middleware.sessions import SessionMiddleware`
- `from app.db.session import init_db`
- `from app.api.routes.auth import router as auth_router`
- `import uvicorn`, `import os`

### Wiring

```python
app = FastAPI(title="Security Vulnerability Lab")

# Vulnerability #4 — hardcoded weak secret key
app.add_middleware(SessionMiddleware, secret_key="super-secret-key-12345")

app.include_router(auth_router)

app.mount("/static/css", StaticFiles(directory="frontend/static/css"), name="css")
app.mount("/static/images", StaticFiles(directory="frontend/static/images"), name="images")

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3001"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
```

### Vulnerability tie-in

- `secret_key="super-secret-key-12345"` literal **is** Vulnerability #4. The string is intentionally short, predictable, and committed to source. No env-var fallback is added at this layer — the comment in the file should state that the literal value is required by the TDD.
- No rate-limit middleware is registered → Vulnerability #7.
- No CSRF middleware is registered → Vulnerability #8.
- Running on `0.0.0.0:3001` matches the TDD default; `PORT` env override is supported for convenience but does not change vulnerability posture.

---

## Phase 7 — Frontend Templates

**Goal:** Build the three HTML pages described in the spec addendum. All three share a fixed header (app title on left, three logos on right) and link `styles.css` from `/static/css/styles.css`.

### `frontend/templates/login.html`

- Split-screen layout.
- **Left panel:** deep-blue gradient (`#0d1b5e → #1a237e → #283593`) with decorative low-opacity circles, "Security Vulnerability Lab" heading, supporting copy, and the three logos.
- **Right panel:** white background, login form with `username` and `password` fields, submit button.
- **JavaScript:** intercept the form submit, `preventDefault()`, build `FormData`, `fetch("/login", { method: "POST", body: formData })`, parse the JSON response, on `data.success === true` set `window.location.href = data.redirect`, else display `data.error` in an inline error element below the form.
- This JS-driven flow is what enables the JSON `success/error` responses from `auth_service.login()` to drive UX without a page reload.

### `frontend/templates/signup.html`

- Same split-screen layout as `login.html`.
- Standard `<form action="/signup" method="POST">` (no JS submit handler required — server returns 302).
- Four fields: `username`, `email`, `password`, `confirm_password`.
- Client-side JS: on submit, check `password === confirm_password`; if not, `preventDefault()` and display "Passwords do not match" inline. Otherwise let the form post normally.
- Inline `<span id="error-message">` for error display (server returns HTML body `"Username already exists"` with status 400 on UNIQUE-constraint failure).

### `frontend/templates/dashboard.html`

- Dashboard layout with a blue-gradient hero banner (`#1a237e → #3949ab`) containing the "Security Vulnerability Lab" title and "Logged in as {{username}}" sub-line, plus a logout button (anchor tag with `href="/logout"`).
- **Mission card** describing the educational purpose.
- **8 vulnerability cards** in a 2-column grid; each card has:
  - A coloured pill-style tag (SQLi=yellow, XSS=red, Session=purple, Brute=orange, Crypto=green, Exposed=blue, CSRF=pink) — note: Vulnerability #2/#3 are both "XSS" (red), Vulnerability #7 has no tag in the spec since it spans all routes.
  - A short title and 1–2 sentence description of the flaw.
- **3 process step cards** ("Find", "Exploit", "Mitigate") on `#1a237e` cards.
- The `{{username}}` placeholder appears verbatim in the HTML — the server replaces it via `str.replace` in the `/welcome` handler.

### Shared assets

- All three templates reference `/static/css/styles.css` and `/static/images/*.png` for the logos.
- No template inheritance / no Jinja — plain HTML.

---

## Phase 8 — Styling (`frontend/static/css/styles.css`)

**Goal:** Implement the responsive visual design specified in §5 of `app-foundation.md`. Single stylesheet shared by all three pages.

### Key tokens (from spec)

- **Primary palette:** `#1a237e`, `#3949ab`, `#283593`, `#0f172a`, `#eef1f8`, `#ffffff`
- **Text colours:** `#1e293b`, `#475569`, `#64748b`, `#c5cae9`, `#1a237e`
- **Typography scale:** main `2rem/800`, section `1.4rem/700`, form heading `1.7rem/700`, card title `0.95rem/700`, body `0.9rem/400`, labels `0.82rem/600`, buttons `1rem/600`
- **Radii:** inputs `8px`, buttons `8px`, cards `10–12px`, tags `6px`
- **Shadows:** header `0 2px 10px rgba(26,35,126,0.08)`, card-hover `0 4px 16px rgba(26,35,126,0.10)`, focus `0 0 0 3px rgba(57,73,171,0.12)`
- **Layout:** fixed `70px` header, two-column auth pages (`~50/50` split), dashboard body `#eef1f8` with hero gradient
- **Vulnerability tag colours** (pill backgrounds): SQLi=yellow, XSS=red, Session=purple, Brute=orange, Crypto=green, Exposed=blue, CSRF=pink
- **Process step cards:** solid `#1a237e` with white text
- **Responsive breakpoints** matching the spec

The CSS file is the single source of truth for all visual styling; HTML templates should not carry inline styles except where unavoidable.

---

## Phase 9 — `CLAUDE.md` at project root

**Goal:** Provide a project-level Claude Code orientation file that summarises context the assistant needs when working in this repo.

### Sections to include

1. **Project context** — security-education lab; intentionally vulnerable; non-production-only.
2. **Development commands** — how to install (`uv sync`), run (`uv run backend/app/main.py` or `uvicorn app.main:app --reload`), and reset the DB (delete `vulnerable_app.db`).
3. **Architecture overview** — backend layout (`app/main.py`, `app/api/routes/auth.py`, `app/services/auth_service.py`, `app/core/security.py`, `app/db/session.py`), frontend layout (`frontend/templates/`, `frontend/static/`), and the `sys.path` shim in `main.py`.
4. **Vulnerability map** — table linking each of the eight vulnerabilities to the file/line that reproduces it.
5. **Frontend-backend integration** — how the login flow uses JS fetch + JSON response, while signup uses a traditional POST + redirect.
6. **Security education context** — explicit warning about non-production use, OWASP alignment, and the "exactly reproduce as specified" framing.
7. **Specification hierarchy** — `docs/PRD.md` (product) → `docs/TDD.md` (technical design) → `.claude/specs/app-foundation.md` (implementation addendum) → this plan.

---

## Phase 10 — Testing and Validation

**Goal:** End-to-end manual verification that every page loads, every flow works, and every vulnerability is demonstrable.

### Pre-flight

1. From the project root, run `uv sync` to materialise dependencies.
2. Confirm no `vulnerable_app.db` exists in the project root (start clean so `init_db()` runs the CREATE TABLE path).
3. Launch the app: `uv run backend/app/main.py` (or `uvicorn app.main:app --host 0.0.0.0 --port 3001` from `backend/`).
4. Confirm Uvicorn reports listening on `0.0.0.0:3001` and the database file appears in the project root.

### Page-load checks

- `curl -I http://localhost:3001/` → expect `302` redirect to `/signup`.
- `curl -I http://localhost:3001/signup` → expect `200`, `Content-Type: text/html`.
- `curl -I http://localhost:3001/login` → expect `200`, `Content-Type: text/html`.
- `curl -I http://localhost:3001/static/css/styles.css` → expect `200`.
- `curl -I http://localhost:3001/static/images/<logo>.png` → expect `200`.

### Signup flow (Vulnerability #1 + #5 surface)

1. `POST /signup` with valid `username`, `email`, `password` → expect `302` to `/login`.
2. Verify `vulnerable_app.db` now contains a row with `username`, `email`, and the MD5 hex digest (no salt).
3. `POST /signup` with the same `username` → expect status `400` and body `"Username already exists"`.
4. **SQLi smoke test:** `POST /signup` with `username = "evil','x','x')--"` → confirm either a 500 or a row with the injected values, demonstrating the concatenation sink.

### Login flow (Vulnerability #1 + #5 surface)

1. `POST /login` with valid credentials → expect `200` JSON `{"success": true, "redirect": "/welcome"}` and a `Set-Cookie` session header.
2. `POST /login` with invalid credentials → expect `401` JSON `{"success": false, "error": "Invalid username or password"}`.
3. **SQLi smoke test:** `POST /login` with `username = "' OR '1'='1"` and any password → expect `200 success: true` if the database has any user (because the concatenated `OR '1'='1'` clause matches all rows).

### Session & dashboard (Vulnerabilities #2 + #4)

1. `GET /welcome` with no session cookie → expect `302` to `/login`.
2. `GET /welcome` with a valid session cookie → expect `200` HTML containing the literal username string from the session.
3. **Stored XSS smoke test:** signup with `username = "<script>alert(1)</script>"`, log in, hit `/welcome` → confirm the response HTML contains the unescaped `<script>` tag (proves Vulnerability #2 and that `str.replace` did not escape).
4. **Session hijack smoke test:** open a browser dev tools, copy the session cookie value, attempt to use it after manually signing the cookie with the hardcoded secret `"super-secret-key-12345"` via `itsdangerous` → confirm a forged cookie is accepted (proves Vulnerability #4).

### Reflected XSS (Vulnerability #3)

1. `GET /search?q=<script>alert(1)</script>` → expect `200` HTML containing the unescaped `<script>` tag in the body (proves Vulnerability #3).

### Exposed database (Vulnerability #6)

1. `curl -O http://localhost:3001/download/db` without any cookie → expect `200` and the file `db` matching `vulnerable_app.db` byte-for-byte (proves Vulnerability #6).

### CSRF & rate limiting (Vulnerabilities #7 + #8)

1. Inspect the login/signup HTML — confirm there is **no** `<input type="hidden" name="csrf_token">` or equivalent (Vulnerability #8).
2. Inspect `main.py` — confirm there is **no** `slowapi`/`fastapi-limiter` middleware and no rate-limit decorator (Vulnerability #7).
3. As a behavioural smoke test, hit `/login` 50 times in quick succession from a single IP — confirm none of them are throttled.

### Logout

1. After logging in, `GET /logout` → expect `302` to `/login` and a session-clearing `Set-Cookie`.
2. Subsequent `GET /welcome` with the cleared cookie → expect `302` to `/login`.

### Sign-off

When all the above pass, the foundation is complete. Each "smoke test" that triggers confirms the corresponding vulnerability is **reproducible**, which is the intended end-state for this educational lab.

---

## Critical Files Summary

**Files to create:**

- `backend/pyproject.toml`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/core/__init__.py`
- `backend/app/core/security.py`
- `backend/app/db/__init__.py`
- `backend/app/db/session.py`
- `backend/app/services/__init__.py`
- `backend/app/services/auth_service.py`
- `backend/app/api/__init__.py`
- `backend/app/api/routes/__init__.py`
- `backend/app/api/routes/auth.py`
- `frontend/templates/login.html`
- `frontend/templates/signup.html`
- `frontend/templates/dashboard.html`
- `frontend/static/css/styles.css`
- `CLAUDE.md` (project root)

**Files referenced but not modified:**

- `pyproject.toml` (umbrella project — already exists)
- `frontend/static/images/*.png` (logos — already exist)
- `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md` (specifications — already exist)

**Files generated at runtime:**

- `vulnerable_app.db` (created by `init_db()` on first run)

---

## Notes for the Implementer

- **Do NOT parameterise the SQL.** Every `+ username`, `+ email`, `+ password`, `+ hashed`, and `+ q` in `auth_service.py` and `auth.py` is intentional. Using `?` placeholders would silently fix Vulnerability #1 and break the educational objective.
- **Do NOT add a salt, a work factor, or `hmac.compare_digest`.** The MD5 path in `security.py` is the entire point of Vulnerability #5.
- **Do NOT add CSRF tokens.** Forms in `login.html` and `signup.html` should ship without hidden CSRF inputs. Vulnerability #8 is the *absence* of that protection.
- **Do NOT add rate-limit middleware.** Even a single global `slowapi.Limiter` would close Vulnerability #7. Resist the urge.
- **Do NOT replace `str.replace('{{username}}', username)` with `html.escape()` or a template engine.** Vulnerability #2 is the unescaped substitution.
- **Keep the sys.path shim.** It is what allows `uv run backend/app/main.py` to resolve `app.*` imports regardless of cwd.

---

*End of plan.*