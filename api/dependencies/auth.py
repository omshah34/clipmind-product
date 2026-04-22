# DEV ONLY — REVERT BEFORE DEPLOY
from typing import Optional
from uuid import UUID
import os
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx

class AuthenticatedUser:
    def __init__(self, user_id: str, email: str, role: str = 'user'):
        self.user_id = UUID(user_id) if isinstance(user_id, str) else user_id
        self.email = email
        self.role = role

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id='00000000-0000-0000-0000-000000000000',
        email='dev@clipmind.ai',
        role='owner'
    )
