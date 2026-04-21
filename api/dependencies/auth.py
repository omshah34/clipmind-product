"""
File: api/dependencies/auth.py
Purpose: Authentication dependencies for FastAPI routes
         Validates JWT tokens from NextAuth and injects authenticated user context
"""

from typing import Optional
from uuid import UUID
import os
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from core.config import settings

logger = logging.getLogger(__name__)

# JWT validation configuration
NEXTAUTH_URL = os.getenv("NEXTAUTH_URL", "http://localhost:3000")
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "")


class AuthenticatedUser:
    """Represents an authenticated user from NextAuth"""
    
    def __init__(self, user_id: str, email: str, role: str = "user"):
        self.user_id = UUID(user_id) if isinstance(user_id, str) else user_id
        self.email = email
        self.role = role


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthenticatedUser:
    """
    Dependency to extract and validate JWT token from Authorization header.
    
    Called automatically on protected routes:
        @router.get("/protected")
        async def protected_route(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.user_id}
    
    Raises HTTPException if token is invalid or missing.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        # Validate token with NextAuth
        user_data = await validate_nextauth_token(token)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return AuthenticatedUser(
            user_id=user_data.get("id"),
            email=user_data.get("email"),
            role=user_data.get("role", "user"),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def validate_nextauth_token(token: str) -> Optional[dict]:
    """
    Validate JWT token by calling NextAuth session endpoint.
    
    This verifies the token is valid, not expired, and comes from our NextAuth instance.
    
    Args:
        token: JWT token from Authorization header
        
    Returns:
        User data dict with id, email, role if valid, None if invalid
    """
    try:
        async with httpx.AsyncClient() as client:
            # Call NextAuth session endpoint to validate token
            # The session endpoint returns user data if token is valid
            response = await client.get(
                f"{NEXTAUTH_URL}/api/auth/session",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
            )
            
            if response.status_code == 200:
                return response.json()
            
            return None
            
    except httpx.TimeoutException:
        logger.error("NextAuth session endpoint timeout")
        return None
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        return None
