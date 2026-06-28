"""SQLite session for the Security Vulnerability Lab.

Intentionally minimal: a single shared connection, no pooling, no ORM.
The schema is intentionally weak (no salt column on `password`) because
this application is an educational reproduction of common web flaws —
see docs/PRD.md and docs/TDD.md for the full vulnerability catalogue.
"""
import sqlite3

# Single shared connection. check_same_thread=False to avoid SQLite's
# threading complaints when FastAPI dispatches across worker threads.
conn = sqlite3.connect("vulnerable_app.db", check_same_thread=False)
conn.row_factory = sqlite3.Row


def init_db() -> None:
    """Create the `users` table if it does not already exist.

    Idempotent — safe to call on every process start.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password TEXT
        )
        """
    )
    conn.commit()
