"""Application entry point for the Security Vulnerability Lab.

This file can be launched as:
  - `uv run backend/app/main.py`  (from the project root)
  - `python -m app.main`          (from inside `backend/`)

The sys.path shim below makes both work, regardless of cwd.
"""
# --- sys.path shim: keep this at the very top, before any app.* imports ---
import pathlib
import sys

# `main.py` lives at backend/app/main.py. For `import app.*` to resolve,
# we need the *parent* of this file's directory — i.e. the directory that
# contains the `app/` package — which is `backend/`.
_BACKEND_DIR = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
# ---------------------------------------------------------------------------

import os

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.db.session import init_db

app = FastAPI(title="Security Vulnerability Lab")

# Vulnerability #4 — Session Hijacking.
# The secret key is hardcoded, short, and committed to source. Anyone
# with read access to this file can forge session cookies at will.
# Do not "fix" this by reading from an env var — the literal value is
# required by the TDD.
app.add_middleware(SessionMiddleware, secret_key="super-secret-key-12345")

app.include_router(auth_router)

# Static asset mounts. Logos live at frontend/static/images/.
app.mount(
    "/static/css",
    StaticFiles(directory="frontend/static/css"),
    name="static-css",
)
app.mount(
    "/static/images",
    StaticFiles(directory="frontend/static/images"),
    name="static-images",
)

# Initialise the DB on import. Safe to call repeatedly.
init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3001"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
