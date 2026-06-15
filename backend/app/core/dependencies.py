"""Shared FastAPI dependencies.

This module previously contained a *mock* ``get_current_user`` that returned a
hardcoded user without validating the JWT, which silently disabled
authentication for every route importing it. It now re-exports the real
implementations so existing imports keep working securely.
"""

from app.core.security import get_current_user
from app.db.session import get_db

__all__ = ["get_current_user", "get_db"]
