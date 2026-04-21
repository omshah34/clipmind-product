"""
File: api/dependencies/__init__.py
Purpose: Make dependencies a Python package
Exports: get_current_user, AuthenticatedUser
"""

from .auth import get_current_user, AuthenticatedUser

__all__ = ["get_current_user", "AuthenticatedUser"]
