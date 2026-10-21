"""Authentication building blocks.

* :mod:`app.auth.sessions` - signed cookie session (``bellpost_session``, 8 hours)
* :mod:`app.auth.tokens` - bearer token issue, verify and revoke
* :mod:`app.auth.csrf` - CSRF tokens for the admin forms
* :mod:`app.auth.passwords` - pbkdf2_sha256 hashing

The API authenticates with ``Authorization: Bearer <token>``; the admin panel
authenticates with the session cookie. Both paths end up in
:class:`app.tenancy.Identity`.
"""

from app.auth import csrf, passwords, sessions, tokens

__all__ = ["csrf", "passwords", "sessions", "tokens"]
