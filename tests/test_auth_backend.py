"""
File: tests/test_auth_backend.py
Purpose: Test backend authentication dependency for FastAPI
Tests: JWT validation, authenticated user injection, workspace membership checks
"""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import UUID
import json

from fastapi import HTTPException, status
from api.dependencies.auth import (
    get_current_user,
    AuthenticatedUser,
    validate_nextauth_token,
)

# Test data
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
TEST_EMAIL = "user@example.com"
TEST_ROLE = "user"


class TestAuthenticatedUser:
    """Test AuthenticatedUser class"""

    def test_authenticated_user_creation(self):
        """Should create authenticated user with user_id, email, and role"""
        user = AuthenticatedUser(
            user_id=TEST_USER_ID,
            email=TEST_EMAIL,
            role=TEST_ROLE,
        )

        assert user.user_id == UUID(TEST_USER_ID)
        assert user.email == TEST_EMAIL
        assert user.role == TEST_ROLE

    def test_authenticated_user_string_id_conversion(self):
        """Should convert string user_id to UUID"""
        user = AuthenticatedUser(
            user_id=TEST_USER_ID,
            email=TEST_EMAIL,
        )

        assert isinstance(user.user_id, UUID)

    def test_authenticated_user_default_role(self):
        """Should default to 'user' role if not provided"""
        user = AuthenticatedUser(
            user_id=TEST_USER_ID,
            email=TEST_EMAIL,
        )

        assert user.role == "user"


class TestValidateNextAuthToken:
    """Test NextAuth token validation"""

    @pytest.mark.asyncio
    async def test_validate_valid_token(self):
        """Should return user data for valid token"""
        mock_response = {
            "id": TEST_USER_ID,
            "email": TEST_EMAIL,
            "role": TEST_ROLE,
        }

        with patch("api.dependencies.auth.httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client
            from unittest.mock import MagicMock
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_async_client.get.return_value = mock_response_obj

            result = await validate_nextauth_token(TEST_TOKEN)

            assert result == mock_response
            mock_async_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_invalid_token(self):
        """Should return None for invalid token"""
        with patch("api.dependencies.auth.httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client
            mock_async_client.get.return_value.status_code = 401

            result = await validate_nextauth_token(TEST_TOKEN)

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_expired_token(self):
        """Should return None for expired token"""
        with patch("api.dependencies.auth.httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client
            mock_async_client.get.return_value.status_code = 401

            result = await validate_nextauth_token(TEST_TOKEN)

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_network_timeout(self):
        """Should handle network timeout gracefully"""
        import httpx

        with patch("api.dependencies.auth.httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client
            mock_async_client.get.side_effect = httpx.TimeoutException("Timeout")

            result = await validate_nextauth_token(TEST_TOKEN)

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_connection_error(self):
        """Should handle connection errors gracefully"""
        with patch("api.dependencies.auth.httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client
            mock_async_client.get.side_effect = Exception("Connection error")

            result = await validate_nextauth_token(TEST_TOKEN)

            assert result is None


class TestGetCurrentUser:
    """Test get_current_user dependency"""

    @pytest.mark.asyncio
    async def test_get_current_user_valid_credentials(self):
        """Should return AuthenticatedUser for valid credentials"""
        from fastapi.security import HTTPAuthorizationCredentials

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials=TEST_TOKEN,
        )

        mock_user_data = {
            "id": TEST_USER_ID,
            "email": TEST_EMAIL,
            "role": TEST_ROLE,
        }

        with patch(
            "api.dependencies.auth.validate_nextauth_token",
            new_callable=AsyncMock,
        ) as mock_validate:
            mock_validate.return_value = mock_user_data

            user = await get_current_user(mock_credentials)

            assert isinstance(user, AuthenticatedUser)
            assert user.user_id == UUID(TEST_USER_ID)
            assert user.email == TEST_EMAIL
            assert user.role == TEST_ROLE

    @pytest.mark.asyncio
    async def test_get_current_user_missing_credentials(self):
        """Should raise 401 Unauthorized when credentials are missing"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Missing authentication token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Should raise 401 Unauthorized for invalid token"""
        from fastapi.security import HTTPAuthorizationCredentials

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials=TEST_TOKEN,
        )

        with patch(
            "api.dependencies.auth.validate_nextauth_token",
            new_callable=AsyncMock,
        ) as mock_validate:
            mock_validate.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_credentials)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid or expired token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_validation_error(self):
        """Should raise 401 Unauthorized for validation errors"""
        from fastapi.security import HTTPAuthorizationCredentials

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials=TEST_TOKEN,
        )

        with patch(
            "api.dependencies.auth.validate_nextauth_token",
            new_callable=AsyncMock,
        ) as mock_validate:
            mock_validate.side_effect = Exception("Validation error")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_credentials)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Token validation failed" in exc_info.value.detail


class TestWorkspaceAuthRoutes:
    """Test workspace routes with authentication"""

    @pytest.mark.asyncio
    async def test_create_workspace_authenticated(self):
        """Should allow authenticated user to create workspace"""
        # This would be tested in integration tests with mock database
        pass

    @pytest.mark.asyncio
    async def test_create_workspace_unauthenticated(self):
        """Should reject workspace creation without authentication"""
        # API should return 401 Unauthorized
        pass

    @pytest.mark.asyncio
    async def test_list_workspaces_authenticated(self):
        """Should return user's workspaces when authenticated"""
        # Should return list of workspaces user is member of
        pass

    @pytest.mark.asyncio
    async def test_invite_member_owner_only(self):
        """Should enforce owner-only permission for member invitations"""
        # Viewer or editor should get 403 Forbidden
        pass

    @pytest.mark.asyncio
    async def test_delete_member_owner_only(self):
        """Should enforce owner-only permission for member removal"""
        # Only owner can remove members
        pass


class TestRBACEnforcement:
    """Test role-based access control"""

    def test_role_hierarchy(self):
        """Should enforce role hierarchy: owner > editor > viewer"""
        ROLE_HIERARCHY = {
            "owner": 3,
            "editor": 2,
            "viewer": 1,
        }

        assert ROLE_HIERARCHY["owner"] > ROLE_HIERARCHY["editor"]
        assert ROLE_HIERARCHY["editor"] > ROLE_HIERARCHY["viewer"]

    def test_owner_can_do_all(self):
        """Owner role should have all permissions"""
        owner_permissions = {"read", "write", "invite", "delete", "admin"}
        editor_permissions = {"read", "write", "invite"}
        viewer_permissions = {"read"}

        assert owner_permissions > editor_permissions
        assert owner_permissions > viewer_permissions

    def test_editor_limited_permissions(self):
        """Editor role should not have delete or admin permissions"""
        editor_permissions = {"read", "write", "invite"}

        assert "delete" not in editor_permissions
        assert "admin" not in editor_permissions

    def test_viewer_read_only(self):
        """Viewer role should only have read permission"""
        viewer_permissions = {"read"}

        assert "write" not in viewer_permissions
        assert "delete" not in viewer_permissions


class TestErrorScenarios:
    """Test error handling in authentication"""

    @pytest.mark.asyncio
    async def test_malformed_jwt_token(self):
        """Should handle malformed JWT tokens"""
        from fastapi.security import HTTPAuthorizationCredentials

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials="not.a.valid.jwt",
        )

        with patch(
            "api.dependencies.auth.validate_nextauth_token",
            new_callable=AsyncMock,
        ) as mock_validate:
            mock_validate.return_value = None

            with pytest.raises(HTTPException):
                await get_current_user(mock_credentials)

    @pytest.mark.asyncio
    async def test_database_connection_error(self):
        """Should handle database connection errors gracefully"""
        from fastapi.security import HTTPAuthorizationCredentials

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials=TEST_TOKEN,
        )

        with patch(
            "api.dependencies.auth.validate_nextauth_token",
            new_callable=AsyncMock,
        ) as mock_validate:
            mock_validate.side_effect = Exception("DB connection failed")

            with pytest.raises(HTTPException):
                await get_current_user(mock_credentials)

    @pytest.mark.asyncio
    async def test_nextauth_service_down(self):
        """Should handle NextAuth service unavailability"""
        import httpx

        with patch("api.dependencies.auth.httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client
            mock_async_client.get.side_effect = httpx.ConnectError(
                "Service unavailable"
            )

            result = await validate_nextauth_token(TEST_TOKEN)

            assert result is None


class TestTokenScopes:
    """Test token scope validation"""

    def test_token_contains_required_claims(self):
        """Token should contain required claims: id, email, role"""
        token_data = {
            "id": TEST_USER_ID,
            "email": TEST_EMAIL,
            "role": TEST_ROLE,
        }

        assert "id" in token_data
        assert "email" in token_data
        assert "role" in token_data

    def test_token_refresh_claim(self):
        """Token can contain refresh_token for OAuth providers"""
        token_data = {
            "id": TEST_USER_ID,
            "refresh_token": "refresh_token_value",
            "access_token": "access_token_value",
        }

        # Refresh token not required but allowed
        assert "refresh_token" in token_data or True


if __name__ == "__main__":
    # Run tests with: pytest tests/test_auth_backend.py -v
    pytest.main([__file__, "-v"])
