"""HTTP route handlers for the Security Vulnerability Lab.

This module is the home of Vulnerabilities #2 (Stored XSS), #3
(Reflected XSS), and #6 (Exposed Database) from the educational
catalogue. The dashboard reads a template from disk and substitutes
the username placeholder with `str.replace` — no escaping. The
search route reflects the `q` query parameter into the response
body without escaping. The `/download/db` route returns the SQLite
file with no authentication check.
"""
from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
import sqlite3

from app.db.session import conn
from app.services.auth_service import login as auth_login
from app.services.auth_service import signup as auth_signup

router = APIRouter()


@router.get("/")
def root():
    """Redirect the bare site root to the signup page."""
    return RedirectResponse(url="/signup", status_code=302)


@router.get("/signup")
def signup_form():
    """Render the signup page from disk.

    Templates are read from disk on every request — no caching,
    no template engine. This matches the spec's "per-request
    template loading" requirement.
    """
    with open("frontend/templates/signup.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.post("/signup")
def signup_post(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    """Delegate to the auth service. On success, the service returns
    a RedirectResponse; on a UNIQUE-constraint violation it returns
    a 400 HTMLResponse with the body "Username already exists"."""
    return auth_signup(username, email, password)


@router.get("/login")
def login_form():
    """Render the login page from disk."""
    with open("frontend/templates/login.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Delegate to the auth service. The service returns a JSONResponse
    so the login form's client-side JavaScript can update the UI
    without a page reload."""
    return auth_login(request, username, password)


@router.get("/download/db")
def download_db():
    """Vulnerability #6 — Exposed Database.

    Returns the SQLite file with no authentication check, no
    session lookup, and no rate limiting. Anyone who can reach
    the server can pull the entire user table (including MD5
    password hashes) in a single GET.
    """
    return FileResponse(
        path="vulnerable_app.db",
        filename="vulnerable_app.db",
        media_type="application/octet-stream",
    )


@router.get("/search")
def search(request: Request):
    """Vulnerability #3 — Reflected XSS.

    The `q` query parameter is interpolated into the SQL `LIKE`
    clause via string concatenation (also a SQLi sink) and into
    the HTML response body without escaping. Errors are returned
    with `str(e)` so tracebacks leak into the response.
    """
    q = request.query_params.get("q", "")
    try:
        # INTENTIONAL SQL INJECTION SINK (additional, beyond auth_service).
        sql = (
            "SELECT username, email FROM users WHERE username LIKE '%"
            + q + "%'"
        )
        rows = conn.execute(sql).fetchall()
    except Exception as e:
        return HTMLResponse(content="Error: " + str(e), status_code=500)

    body = (
        "<!doctype html><html><head><title>Search</title>"
        "<link rel='stylesheet' href='/static/css/styles.css'></head><body>"
        "<header class='app-header'>"
        "<div class='app-title'>Security Vulnerability Lab</div>"
        "<div class='header-logos'>"
        "<img src='/static/images/PUCIT_Logo.png' alt='PUCIT'>"
        "<img src='/static/images/blue-logo-scl2.png' alt='SCL'>"
        "<img src='/static/images/blue-logo-scl2.png' alt='SCL'>"
        "</div></header>"
        "<main class='search-page'>"
        "<h1>Search results for: " + q + "</h1>"
        "<ul class='search-results'>"
    )
    for r in rows:
        body += "<li>" + r["username"] + " &mdash; " + r["email"] + "</li>"
    body += "</ul>"
    body += (
        "<p><a class='btn-link' href='/welcome'>&larr; Back to dashboard</a></p>"
        "</main></body></html>"
    )
    return HTMLResponse(content=body)


@router.get("/welcome")
def welcome(request: Request):
    """Vulnerability #2 — Stored XSS.

    If no session is present, redirect to /login. Otherwise load
    the dashboard template from disk and replace `{{username}}`
    with the raw session value via `str.replace`. No HTML
    escaping is applied, so a username of `<script>alert(1)</script>`
    executes in the browser of every visitor.
    """
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    username = request.session.get("username", "")
    with open("frontend/templates/dashboard.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{username}}", username)
    return HTMLResponse(content=html)


@router.get("/logout")
def logout(request: Request):
    """Clear the session and redirect to /login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
