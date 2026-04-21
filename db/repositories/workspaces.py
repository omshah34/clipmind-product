"""Workspace repository facade."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from db.connection import engine

def create_workspace(user_id: str, name: str, slug: str | None = None) -> dict:
    from uuid import uuid4
    if not slug:
        slug = name.lower().replace(" ", "-") + "-" + uuid4().hex[:4]
    
    query = text(
        """
        INSERT INTO workspaces (owner_id, name, slug)
        VALUES (:owner_id, :name, :slug)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(query, {"owner_id": user_id, "name": name, "slug": slug}).one()
    return dict(row._mapping)

def list_user_workspaces(user_id: str) -> list[dict]:
    query = text(
        """
        SELECT w.*, wm.role 
        FROM workspaces w
        LEFT JOIN workspace_members wm ON wm.workspace_id = w.id AND wm.user_id = :user_id
        WHERE w.owner_id = :user_id OR wm.user_id = :user_id
        ORDER BY w.created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": user_id}).fetchall()
    return [dict(row._mapping) for row in rows]

def add_workspace_member(workspace_id: str, user_id: str, role: str = "editor") -> dict:
    query = text(
        """
        INSERT INTO workspace_members (workspace_id, user_id, role)
        VALUES (:workspace_id, :user_id, :role)
        ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query, {"workspace_id": workspace_id, "user_id": user_id, "role": role}
        ).one()
    return dict(row._mapping)

def create_workspace_client(workspace_id: str, client_name: str, client_contact_email: str | None = None, description: str | None = None) -> dict:
    query = text(
        """
        INSERT INTO workspace_clients (workspace_id, client_name, client_contact_email, description)
        VALUES (:workspace_id, :client_name, :email, :desc)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query, 
            {
                "workspace_id": workspace_id, 
                "client_name": client_name, 
                "email": client_contact_email, 
                "desc": description
            }
        ).one()
    return dict(row._mapping)

def create_client_portal(workspace_id: str, client_id: str, portal_slug: str, branding: dict | None = None) -> dict:
    query = text(
        """
        INSERT INTO client_portals (workspace_id, client_id, portal_slug, branding_json)
        VALUES (:workspace_id, :client_id, :slug, :branding)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "workspace_id": workspace_id,
                "client_id": client_id,
                "slug": portal_slug,
                "branding": json.dumps(branding or {})
            }
        ).one()
    return dict(row._mapping)

def log_workspace_audit(workspace_id: str, action: str, user_id: str | None = None, resource_type: str = "general", resource_id: str | None = None, details: dict | None = None) -> None:
    query = text(
        """
        INSERT INTO workspace_audit_logs (workspace_id, user_id, action, resource_type, resource_id, details_json)
        VALUES (:workspace_id, :user_id, :action, :type, :rid, :details)
        """
    )
    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "action": action,
                "type": resource_type,
                "rid": resource_id,
                "details": json.dumps(details or {})
            }
        )
