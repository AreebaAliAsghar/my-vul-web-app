"""Authentication service.

The SQL queries in this module are intentionally built with string
concatenation. This is Vulnerability #1 (SQL Injection) in the
educational catalogue — see docs/PRD.md and docs/TDD.md. Do not
"fix" this by switching to parameterised queries; doing so would
silently remove the vulnerability the lab is designed to expose.
"""
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import sqlite3

from app.core.security import hash_password
from app.db.session import conn


def signup(username: str, email: str, password: str):
    """Insert a new user via string-concatenated SQL.

    Vulnerability #1 (SQL Injection): user input is interpolated
    directly into the INSERT statement. A `username` containing
    a single quote will break the statement or, in the SQLite
    default config, produce an error.
    """
    if not username or not email or not password:
        raise ValueError("All fields are required")

    hashed = hash_password(password)

    # INTENTIONAL SQL INJECTION SINK — do not parameterise.
    query = (
        "INSERT INTO users (username, email, password) VALUES ('"
        + username + "', '" + email + "', '" + hashed + "')"
    )
    try:
        conn.execute(query)
        conn.commit()
    except sqlite3.IntegrityError:
        return HTMLResponse(
            content="Username already exists",
            status_code=400,
        )

    return RedirectResponse(url="/login", status_code=302)


def login(request, username: str, password: str):
    """Authenticate via string-concatenated SQL and set session keys.

    Vulnerability #1 (SQL Injection): a `username` of the form
    `' OR '1'='1` will return the first row in the table, granting
    access without a valid password.
    """
    if not username or not password:
        return JSONResponse(
            content={"success": False, "error": "Username and password are required"},
            status_code=400,
        )

    hashed = hash_password(password)

    # INTENTIONAL SQL INJECTION SINK — do not parameterise.
    query = (
        "SELECT * FROM users WHERE username = '"
        + username + "' AND password = '" + hashed + "'"
    )
    row = conn.execute(query).fetchone()

    if row is None:
        return JSONResponse(
            content={"success": False, "error": "Invalid username or password"},
            status_code=401,
        )

    request.session["user_id"] = row["id"]
    request.session["username"] = row["username"]
    request.session["email"] = row["email"]

    return JSONResponse(content={"success": True, "redirect": "/welcome"})
