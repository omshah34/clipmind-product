"""File: api/routes/workspaces.py
Purpose: Real workspace, member, client, portal, and audit log endpoints.
         Includes RBAC and Client Portal Approval workflows (Phase 1).
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import text

from api.dependencies.auth import AuthenticatedUser, get_current_user
from api.dependencies.workspace import require_workspace_role
from db.repositories.workspaces import (
    add_workspace_member,
    create_client_portal,
    create_workspace_client,
    list_user_workspaces,
    log_workspace_audit,
    engine,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class MemberInvite(BaseModel):
    email: str
    role: str = "editor"


class ClientCreate(BaseModel):
    client_name: str
    contact_email: str | None = None
    description: str | None = None


class PortalSubmissionCreate(BaseModel):
    job_id: str
    expires_in_days: int = 7


class PortalSubmissionReview(BaseModel):
    status: str  # 'approved', 'rejected', 'changes_requested'
    client_feedback: str | None = None
    approved_clip_indices: list[int] | None = None


def _frontend_base() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")


@router.get("/")
def list_workspaces(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    workspaces = list_user_workspaces(user.user_id)
    return {"workspaces": workspaces}


@router.get("/{workspace_id}/members")
def list_members(
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "editor", "viewer"]))
) -> list[dict]:
    workspace_id = workspace_context["workspace_id"]
    query = text(
        """
        SELECT
            wm.id AS member_id,
            wm.user_id,
            COALESCE(u.email, wm.user_id) AS email,
            wm.role,
            wm.joined_at
        FROM workspace_members wm
        LEFT JOIN users u ON u.id = wm.user_id
        WHERE wm.workspace_id = :workspace_id
        ORDER BY wm.joined_at ASC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"workspace_id": workspace_id}).fetchall()
    return [dict(row._mapping) for row in rows]


@router.post("/{workspace_id}/members", status_code=201)
def add_member(
    payload: MemberInvite,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
) -> dict:
    workspace_id = workspace_context["workspace_id"]
    user_id = workspace_context["user_id"]
    
    with engine.begin() as connection:
        user_row = connection.execute(
            text(
                """
                INSERT INTO users (email, full_name)
                VALUES (:email, :full_name)
                ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
                RETURNING id, email
                """
            ),
            {
                "email": payload.email,
                "full_name": payload.email.split("@", 1)[0].replace(".", " ").title(),
            },
        ).one()

    member = add_workspace_member(workspace_id, user_row.id, payload.role)
    log_workspace_audit(
        workspace_id,
        "member.invited",
        user_id=user_id,
        resource_type="workspace_member",
        resource_id=member["id"],
        details={"email": payload.email, "role": payload.role},
    )

    return {
        "member_id": member["id"],
        "user_id": member["user_id"],
        "email": payload.email,
        "role": member["role"],
        "joined_at": member["joined_at"],
    }


@router.delete("/{workspace_id}/members/{member_id}")
def remove_member(
    member_id: str,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
) -> dict:
    workspace_id = workspace_context["workspace_id"]
    user_id = workspace_context["user_id"]
    
    query = text(
        """
        DELETE FROM workspace_members
        WHERE id = :member_id AND workspace_id = :workspace_id
        """
    )
    with engine.begin() as connection:
        result = connection.execute(query, {"member_id": member_id, "workspace_id": workspace_id})
    if result.rowcount <= 0:
        raise HTTPException(status_code=404, detail="Member not found")

    log_workspace_audit(
        workspace_id,
        "member.removed",
        user_id=user_id,
        resource_type="workspace_member",
        resource_id=member_id,
    )
    return {"status": "deleted", "member_id": member_id}


@router.get("/{workspace_id}/clients")
def list_clients(
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "editor", "viewer"])),
) -> list[dict]:
    workspace_id = workspace_context["workspace_id"]
    query = text(
        """
        SELECT
            id AS client_id,
            client_name,
            client_contact_email AS contact_email,
            description,
            CASE WHEN is_active = 1 OR is_active = TRUE THEN 'active' ELSE 'inactive' END AS client_status,
            created_at
        FROM workspace_clients
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"workspace_id": workspace_id}).fetchall()
    return [dict(row._mapping) for row in rows]


@router.post("/{workspace_id}/clients", status_code=201)
def add_client(
    payload: ClientCreate,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
) -> dict:
    workspace_id = workspace_context["workspace_id"]
    user_id = workspace_context["user_id"]
    
    client = create_workspace_client(
        workspace_id=workspace_id,
        client_name=payload.client_name,
        client_contact_email=payload.contact_email,
        description=payload.description,
    )
    log_workspace_audit(
        workspace_id,
        "client.created",
        user_id=user_id,
        resource_type="client",
        resource_id=client["id"],
        details={"client_name": payload.client_name},
    )
    return {
        "client_id": client["id"],
        "client_name": client["client_name"],
        "contact_email": client.get("client_contact_email"),
        "description": client.get("description"),
        "client_status": "active" if client.get("is_active", 1) else "inactive",
        "created_at": client["created_at"],
    }


@router.post("/{workspace_id}/clients/{client_id}/portal", status_code=201)
def create_portal(
    client_id: str,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
) -> dict:
    workspace_id = workspace_context["workspace_id"]
    user_id = workspace_context["user_id"]
    
    portal_slug = f"{client_id[:8]}-{uuid4().hex[:8]}"
    token_secret = uuid4().hex
    portal = create_client_portal(
        workspace_id=workspace_id,
        client_id=client_id,
        portal_slug=portal_slug,
        branding={},
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE client_portals
                SET token_secret = :token_secret
                WHERE id = :portal_id
                """
            ),
            {"portal_id": portal["id"], "token_secret": token_secret},
        )

    log_workspace_audit(
        workspace_id,
        "portal.created",
        user_id=user_id,
        resource_type="client_portal",
        resource_id=portal["id"],
        details={"client_id": client_id},
    )

    return {
        "portal_id": portal["id"],
        "client_id": client_id,
        "portal_token": token_secret,
        "portal_url": f"{_frontend_base()}/portal/{portal_slug}?token={token_secret}",
        "portal_status": "active" if portal.get("is_active", 1) else "inactive",
    }


@router.get("/{workspace_id}/portals")
def list_portals(
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "editor", "viewer"])),
) -> list[dict]:
    workspace_id = workspace_context["workspace_id"]
    query = text(
        """
        SELECT
            cp.id AS portal_id,
            cp.client_id,
            COALESCE(cp.token_secret, cp.portal_slug) AS portal_token,
            cp.portal_slug,
            CASE WHEN cp.is_active = 1 OR cp.is_active = TRUE THEN 'active' ELSE 'inactive' END AS portal_status
        FROM client_portals cp
        WHERE cp.workspace_id = :workspace_id
        ORDER BY cp.created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"workspace_id": workspace_id}).fetchall()

    return [
        {
            "portal_id": row.portal_id,
            "client_id": row.client_id,
            "portal_token": row.portal_token,
            "portal_url": f"{_frontend_base()}/portal/{row.portal_slug}?token={row.portal_token}",
            "portal_status": row.portal_status,
        }
        for row in rows
    ]


@router.get("/{workspace_id}/audit-logs")
def list_audit_logs(
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
) -> list[dict]:
    workspace_id = workspace_context["workspace_id"]
    query = text(
        """
        SELECT
            wal.id AS log_id,
            wal.action,
            COALESCE(u.email, wal.user_id, 'system') AS performed_by,
            wal.resource_type,
            wal.created_at AS timestamp
        FROM workspace_audit_logs wal
        LEFT JOIN users u ON u.id = wal.user_id
        WHERE wal.workspace_id = :workspace_id
        ORDER BY wal.created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"workspace_id": workspace_id}).fetchall()
    return [dict(row._mapping) for row in rows]

# ==============================================================================
# Phase 1: Agency Workspaces - Portal Submissions
# ==============================================================================

@router.post("/{workspace_id}/portals/{portal_id}/submissions", status_code=201)
def create_portal_submission(
    portal_id: str,
    payload: PortalSubmissionCreate,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "editor"])),
):
    """
    Agency submits a specific job (containing generated clips) to a client portal 
    for approval using a unique shareable review link.
    """
    workspace_id = workspace_context["workspace_id"]
    user_id = workspace_context["user_id"]
    
    submission_token = uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    
    with engine.begin() as connection:
        # Verify portal belongs to the workspace
        portal_check = connection.execute(
            text("SELECT 1 FROM client_portals WHERE id = :portal_id AND workspace_id = :workspace_id"),
            {"portal_id": portal_id, "workspace_id": workspace_id}
        ).scalar()
        if not portal_check:
            raise HTTPException(status_code=404, detail="Portal not found.")

        # Create submission
        row_id = connection.execute(
            text(
                """
                INSERT INTO portal_submissions 
                (portal_id, job_id, submission_token, expires_at)
                VALUES (:portal_id, :job_id, :token, :expires_at)
                RETURNING id
                """
            ),
            {
                "portal_id": portal_id, 
                "job_id": payload.job_id,
                "token": submission_token,
                "expires_at": expires_at
            }
        ).scalar()
        
    log_workspace_audit(
        workspace_id,
        "submission.created",
        user_id=user_id,
        resource_type="portal_submission",
        resource_id=row_id,
        details={"job_id": payload.job_id}
    )
    
    return {
        "submission_id": row_id,
        "submission_token": submission_token,
        "review_link": f"{_frontend_base()}/review/{submission_token}",
        "expires_at": expires_at.isoformat()
    }


# This is a PUBLIC route so Clients can review without signing in.
@router.post("/public/submissions/{submission_token}/review")
def review_portal_submission(
    submission_token: str,
    payload: PortalSubmissionReview
):
    """
    Clients use this public endpoint (via their white-label review link) 
    to approve or request changes on clips.
    """
    with engine.begin() as connection:
        # Check if submission is valid and not expired
        submission = connection.execute(
            text(
                """
                SELECT id, portal_id, job_id, status, expires_at
                FROM portal_submissions
                WHERE submission_token = :token
                """
            ),
            {"token": submission_token}
        ).fetchone()
        
        if not submission:
            raise HTTPException(status_code=404, detail="Invalid review link.")
            
        if submission.expires_at and submission.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Review link has expired.")
            
        approved_indices_json = json.dumps(payload.approved_clip_indices) if payload.approved_clip_indices else None
            
        _ts = "NOW()" if engine.dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
        connection.execute(
            text(
                f"""
                UPDATE portal_submissions
                SET status = :status,
                    client_feedback = :feedback,
                    approved_clip_indices = :approved_indices,
                    updated_at = {_ts}
                WHERE submission_token = :token
                """
            ),
            {
                "status": payload.status,
                "feedback": payload.client_feedback,
                "approved_indices": approved_indices_json,
                "token": submission_token
            }
        )
        
    return {"message": "Review submitted successfully", "status": payload.status}
