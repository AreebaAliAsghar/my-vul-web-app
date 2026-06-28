# Security Vulnerability Lab

> **⚠️ Educational use only.** This application is **deliberately vulnerable**.
> Do **not** deploy it to production, do **not** expose it to the public
> internet, and do **not** run it against systems you do not own or have
> explicit permission to test. Use it only in a safe, isolated environment
> (e.g. `localhost`) for security education.

An intentionally vulnerable FastAPI web application built for OWASP-style
security training. **Eight** common web flaws are present and demonstrable.
The goal is to find each one, exploit it, and then research how a real-world
application would defend against it.

---

## Table of contents

- [Quick start](#quick-start)
- [The eight vulnerabilities](#the-eight-vulnerabilities)
- [Project structure](#project-structure)
- [Exploitation walkthrough](#exploitation-walkthrough)
- [Frontend ↔ backend flow](#frontend--backend-flow)
- [Reset, configuration, and dev commands](#reset-configuration-and-dev-commands)
- [Documentation](#documentation)
- [License & safety](#license--safety)

---

## Quick start

You need [Python 3.12+](https://www.python.org/) and
[uv](https://docs.astral.sh/uv/) installed.

```bash
# 1. Clone the repository
git clone https://github.com/AreebaAliAsghar/my-vul-web-app.git
cd my-vul-web-app

# 2. Install dependencies
uv sync

# 3. Run the backend (default port 3001)
uv run backend/app/main.py
```

Then open <http://localhost:3002> in your browser.

On first run, `init_db()` creates a SQLite database (`vulnerable_app.db`) in
the project root. There are **no default users** — register one via
`/signup`, or exploit the SQL injection to log in as anyone.

---

## The eight vulnerabilities

Each one is intentional. The dashboard at `/welcome` shows the same list.

| #  | Vulnerability                   | File / route                                        | Mechanism (the bug)                                                              |
|----|---------------------------------|-----------------------------------------------------|----------------------------------------------------------------------------------|
| 1  | SQL Injection (login & signup)  | `backend/app/services/auth_service.py`              | `INSERT` / `SELECT` built with `+` concatenation, not parameter binding          |
| 2  | Stored XSS (dashboard)          | `backend/app/api/routes/auth.py` (`/welcome`)       | `str.replace("{{username}}", username)` with no `html.escape`                    |
| 3  | Reflected XSS (search)          | `backend/app/api/routes/auth.py` (`/search`)        | Query param `q` interpolated into `LIKE` clause and HTML body                    |
| 4  | Session hijacking               | `backend/app/main.py`                               | `SessionMiddleware(secret_key="super-secret-key-12345")` — literal in source     |
| 5  | Weak password storage           | `backend/app/core/security.py`                      | `hashlib.md5(password).hexdigest()`, no salt, no work factor                      |
| 6  | Exposed database download       | `backend/app/api/routes/auth.py` (`/download/db`)   | `FileResponse("vulnerable_app.db")` served to anyone, no auth check              |
| 7  | No rate limiting                | All routes                                          | No middleware, no decorator, no failed-login backoff                             |
| 8  | CSRF (no tokens)                | All forms (`/signup`, `/login`)                     | No token generation, no `SameSite` cookie enforcement                            |

The vulnerabilities **must remain in place** — they are the educational
content of the lab. Do not "fix" them while exploring.

---

## Project structure

```
my-vul-web-app/
├── backend/                       Python package (hatchling build)
│   ├── pyproject.toml             FastAPI + uvicorn + python-multipart + itsdangerous
│   └── app/
│       ├── main.py                FastAPI app, SessionMiddleware, static mounts
│       ├── core/security.py       MD5 password helpers
│       ├── db/session.py          SQLite connection + init_db()
│       ├── services/
│       │   └── auth_service.py    signup/login business logic
│       └── api/routes/
│           └── auth.py            all HTTP routes (/login, /signup, /welcome, …)
│
├── frontend/
│   ├── templates/                 Plain HTML, read from disk per request
│   │   ├── login.html
│   │   ├── signup.html
│   │   └── dashboard.html
│   └── static/
│       ├── css/styles.css
│       └── images/                PUCIT_Logo.png, blue-logo-scl2.png
│
├── docs/                          Product & technical specs
├── CLAUDE.md                      Orientation for AI assistants
└── README.md                      ← you are here
```

No build step for the frontend. No template engine, no JS framework, no
asset pipeline — just HTML, one CSS file, two PNGs, and a touch of vanilla
JS in the login form.

---

## Exploitation walkthrough

You can do these in any order. The first three are the easiest and form the
intended on-ramp.

### 1. SQL injection → log in as any user without knowing the password

On `/login`, submit the username field as:

```
' OR 1=1 --
```

…and any value in the password field. Because the `SELECT` is built with
string concatenation, this bypasses the `AND password = '...'` clause
entirely. The server returns `{"success": true, "redirect": "/welcome"}`
and you land on the dashboard.

Bonus: a duplicate `username` on `/signup` triggers an `IntegrityError`
that returns 400 with the literal message `"Username already exists"` —
proof the query was assembled without parameter binding.

### 2. Stored XSS → run JavaScript on every visitor's dashboard

Sign up with the username:

```
<b onclick="alert('XSS')">click me</b>
```

Log in with any account. The dashboard greets you with a live `<b>` tag
instead of escaped text. The username is rendered with `str.replace(...)`
and never HTML-escaped.

### 3. Reflected XSS → run JavaScript on the search page

Visit:

```
/search?q=<script>alert('XSS')</script>
```

The `q` value is interpolated into both the SQL `LIKE '%...%'` clause and
the HTML response body. There is no escaping and no Content-Security-Policy.

### 4. Session hijacking → forge any session cookie

Open `backend/app/main.py`. The `SessionMiddleware` is initialised with the
literal `secret_key="super-secret-key-12345"`. Anyone with read access to
the source can mint a valid cookie with `itsdangerous.URLSafeSerializer`,
pick any `user_id`, and impersonate that account.

### 5. Weak password storage → crack every password instantly

Sign up, then dump the database with vulnerability #6. Open the `password`
column — you'll see a 32-character hex string. That's MD5, unsalted. Look
any password up on a rainbow table or run `hashcat -m 0` against the file.

### 6. Database download → exfiltrate the user table in one request

While logged out:

```
curl -o vulnerable_app.db http://localhost:3001/download/db
```

The route returns the raw SQLite file with no authentication check. Open
it in any SQLite browser to see every email and every MD5 hash.

### 7. No rate limiting → brute-force logins at full speed

```bash
for pw in $(cat wordlist.txt); do
  curl -s -X POST http://localhost:3001/login \
       -F "username=admin" -F "password=$pw" \
       | grep -q '"success":true' && echo "FOUND: $pw" && break
done
```

There is no per-IP throttle, no failed-login counter, no captcha. The only
limit is your bandwidth.

### 8. CSRF → make the victim's browser do things on their behalf

While logged into the lab in one tab, open this in another tab:

```html
<form action="http://localhost:3001/login" method="POST">
  <input name="username" value="attacker">
  <input name="password" value="attacker">
</form>
<script>document.forms[0].submit()</script>
```

There are no CSRF tokens on any form, no `SameSite` cookie attribute, and
no `Origin`/`Referer` check on the server. A cross-site form post drives
the victim's authenticated session.

---

## Frontend ↔ backend flow

| Flow          | Mechanism                                                                                                              |
|---------------|------------------------------------------------------------------------------------------------------------------------|
| Signup        | Standard HTML `<form action="/signup" method="POST">` → server 302-redirects to `/login` on success, or 400 HTML on duplicate username. |
| Login         | JS-driven `fetch('/login', { method: 'POST', body: formData })` → server returns JSON `{success, redirect}` or `{success: false, error}`. The form's `preventDefault()` swaps a redirect for an inline error. |
| Logout        | `GET /logout` → server clears the session and 302s to `/login`.                                                         |
| Dashboard     | `GET /welcome` → server checks `request.session['user_id']`; redirects to `/login` if missing, otherwise renders `dashboard.html` and `str.replace`'s `{{username}}`. |
| Search        | `GET /search?q=...` → server renders a small inline HTML page; tracebacks leak via `HTMLResponse(content="Error: " + str(e))`. |
| DB download   | `GET /download/db` → server returns the SQLite file with no auth check (vulnerability #6).                             |

---

## Reset, configuration, and dev commands

```bash
# Wipe the SQLite database (next launch will recreate the schema)
rm -f vulnerable_app.db

# Run on a different port
PORT=4000 uv run backend/app/main.py

# Hot-reload during development (run from inside backend/)
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 3001

# Run the test suite (currently a scaffold — no tests yet)
cd backend && uv run --extra dev pytest
```

The app writes `vulnerable_app.db` in whatever directory you launched it
from. To keep the project root tidy, run from a dedicated directory or add
the file to your global `.gitignore`.

---

## Documentation

| Doc                                                | Purpose                                                                |
|----------------------------------------------------|------------------------------------------------------------------------|
| [`CLAUDE.md`](CLAUDE.md)                           | Orientation for AI coding assistants working in this repo.             |
| [`docs/PRD.md`](docs/PRD.md)                       | Product requirements, vulnerability catalogue, user stories.           |
| [`docs/TDD.md`](docs/TDD.md)                       | Technical design — schema, endpoint contract, default port.            |
| [`.claude/specs/app-foundation.md`](.claude/specs/app-foundation.md) | Implementation addendum (visual design, flows, validation).            |
| [`.claude/specs/app-foundation-plan.md`](.claude/specs/app-foundation-plan.md) | Phase-by-phase build plan used to scaffold the app.        |

When changing behaviour, **update the spec first, then the code**. The
intentional vulnerabilities are the feature.

---

## License & safety

This project is provided **as-is for educational use**. There is no warranty
of any kind. You are solely responsible for how you use it.

**Do not** point this application at any host you do not own or have
explicit written permission to test. The exposed database endpoint, the
hardcoded session secret, and the lack of rate limiting are not bugs to be
fixed in this lab — they are the lesson. Always run it on `localhost` (or a
private, isolated VM) and never expose it to the public internet.

If you fork this project to "fix" the vulnerabilities for production use,
**don't** — start from scratch using a real framework's security defaults
(parameterised queries, Argon2 / bcrypt, `SameSite=Lax` cookies, CSRF
tokens, rate-limit middleware, output escaping). This codebase will not
teach you those defaults and patching it will give you a false sense of
security.
