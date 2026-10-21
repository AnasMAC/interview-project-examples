"""Password hashing.

Hashes are ``pbkdf2_sha256`` (werkzeug's format, 600k iterations) and are
verified in constant time by werkzeug. Demo accounts use
``DEMO-<slug>-<role>`` passwords, e.g. ``DEMO-brightpath-admin``; they are
committed on purpose and are not usable outside the local demo stack.
"""

from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

PBKDF2_METHOD = "pbkdf2:sha256:600000"
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    """Return the ``pbkdf2_sha256`` hash of ``password``."""
    return generate_password_hash(password, method=PBKDF2_METHOD)


def check_password(password_hash: str, password: str) -> bool:
    """Constant-time check of a password against a stored hash."""
    return check_password_hash(password_hash, password)


def demo_password(slug: str, role: str) -> str:
    """The documented password for a demo account."""
    return f"DEMO-{slug}-{role}"
