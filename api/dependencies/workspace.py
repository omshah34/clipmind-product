"""File: api/dependencies/workspace.py
Purpose: Dependencies for Workspace RBAC (Role-Based Access Control)
"""
from typing import Callable, Sequence
from fastapi import Depends, HTTPException
from sqlalchemy import text

from api.dependencies.auth import AuthenticatedUser, get_current_user
from db.connection import engine

def require_workspace_role(allowed_roles: Sequence[str] = ("owner", "admin", "editor", "viewer")) -> Callable:
    """Dependency to check if the user has one of the allowed roles in the workspace."""
    def _verify_role(
        workspace_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> dict:
        query = text(
            """
            SELECT 
                w.owner_id,
                wm.role AS member_role
            FROM workspaces w
            LEFT JOIN workspace_members wm 
              ON wm.workspace_id = w.id AND wm.user_id = :user_id
            WHERE w.id = :workspace_id
            LIMIT 1
            """
        )
        with engine.connect() as connection:
            row = connection.execute(
                query, {"workspace_id": workspace_id, "user_id": user.user_id}
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Workspace not found.")

        # If user is the workspace owner, they bypass RBAC checks and act as 'owner'
        is_owner = row.owner_id == user.user_id
        actual_role = "owner" if is_owner else row.member_role

        if not actual_role:
            raise HTTPException(status_code=403, detail="Not a member of this workspace.")

        if actual_role not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail=f"Requires one of roles {allowed_roles}. You have '{actual_role}'."
            )
            
        return {
            "workspace_id": workspace_id,
            "user_id": user.user_id,
            "role": actual_role
        }

    return _verify_role
