"""Tests for Workspace Agency Moat."""

import pytest
from db.repositories.workspaces import create_workspace, add_workspace_member, list_user_workspaces

def test_workspace_lifecycle():
    # Setup - Using a mock user_id
    from db.connection import engine
    from sqlalchemy import text
    from uuid import uuid4
    
    owner_id = f"test-user-{uuid4().hex[:8]}"
    member_id = f"test-user-{uuid4().hex[:8]}"
    
    # Pre-create users to satisfy Foreign Key constraints
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email) VALUES (:id, :email) ON CONFLICT DO NOTHING"), {"id": owner_id, "email": f"{owner_id}@test.com"})
        conn.execute(text("INSERT INTO users (id, email) VALUES (:id, :email) ON CONFLICT DO NOTHING"), {"id": member_id, "email": f"{member_id}@test.com"})

    # 1. Create Workspace
    ws = create_workspace(owner_id, "Test Agency")
    assert ws["name"] == "Test Agency"
    assert ws["owner_id"] == owner_id
    
    # 2. Add Member
    membership = add_workspace_member(ws["id"], member_id, "editor")
    assert membership["role"] == "editor"
    
    # 3. List
    workspaces = list_user_workspaces(member_id)
    assert any(w["id"] == ws["id"] for w in workspaces)
    
    # 4. Verify Role in List
    for w in workspaces:
        if w["id"] == ws["id"]:
            assert w["role"] == "editor"
