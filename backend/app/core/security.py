"""Intentionally weak password hashing.

These helpers use MD5 with no salt and no work factor. This is
Vulnerability #5 in the educational catalogue (see docs/PRD.md and
docs/TDD.md). Do not use this module in any real application.
"""
import hashlib


def hash_password(password: str) -> str:
    """Return the MD5 hex digest of `password` with no salt."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff MD5(plain) == hashed.

    Plain string equality is intentional — constant-time comparison is
    not the educational point of this lab.
    """
    return hash_password(plain) == hashed
