"""add_workspaces_agency_moat

Revision ID: 8c8beb4e1a48
Revises: b8a9bdff86cc
Create Date: 2026-04-21 18:23:00.250302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c8beb4e1a48'
down_revision: Union[str, None] = 'b8a9bdff86cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'
    
    id_default = "(gen_random_uuid()::text)" if is_postgres else "NULL"
    timestamptz = "TIMESTAMPTZ" if is_postgres else "DATETIME"
    now = "NOW()" if is_postgres else "CURRENT_TIMESTAMP"

    # Cleanup any legacy state to ensure clean Phase 4 foundation
    cascade = "CASCADE" if is_postgres else ""
    op.execute(f"DROP TABLE IF EXISTS workspace_audit_logs {cascade};")
    op.execute(f"DROP TABLE IF EXISTS portal_submissions {cascade};")
    op.execute(f"DROP TABLE IF EXISTS client_portals {cascade};")
    op.execute(f"DROP TABLE IF EXISTS workspace_clients {cascade};")
    op.execute(f"DROP TABLE IF EXISTS workspace_members {cascade};")
    op.execute(f"DROP TABLE IF EXISTS workspaces {cascade};")

    # 001 Workspaces
    op.execute(f"""
        CREATE TABLE workspaces (
            id                  TEXT    PRIMARY KEY DEFAULT {id_default},
            owner_id            TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name                TEXT    NOT NULL,
            slug                TEXT    UNIQUE,
            tier                TEXT    NOT NULL DEFAULT 'starter',
            settings            TEXT    NOT NULL DEFAULT '{{}}',
            created_at          {timestamptz} DEFAULT {now},
            updated_at          {timestamptz} DEFAULT {now}
        );
    """)

    # 002 Workspace Members
    op.execute(f"""
        CREATE TABLE workspace_members (
            id                  TEXT    PRIMARY KEY DEFAULT {id_default},
            workspace_id        TEXT    NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id             TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role                TEXT    NOT NULL DEFAULT 'viewer',
            joined_at           {timestamptz} DEFAULT {now},
            UNIQUE(workspace_id, user_id)
        );
    """)

    # 003 Workspace Clients
    op.execute(f"""
        CREATE TABLE workspace_clients (
            id                    TEXT    PRIMARY KEY DEFAULT {id_default},
            workspace_id          TEXT    NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            client_name           TEXT    NOT NULL,
            client_contact_email  TEXT,
            description           TEXT,
            is_active             BOOLEAN DEFAULT TRUE,
            created_at            {timestamptz} DEFAULT {now},
            updated_at            {timestamptz} DEFAULT {now}
        );
    """)

    # 004 Client Portals
    op.execute(f"""
        CREATE TABLE client_portals (
            id                  TEXT    PRIMARY KEY DEFAULT {id_default},
            workspace_id        TEXT    NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            client_id           TEXT    NOT NULL REFERENCES workspace_clients(id) ON DELETE CASCADE,
            portal_slug         TEXT    UNIQUE NOT NULL,
            token_secret        TEXT,
            branding_json       TEXT    DEFAULT '{{}}',
            is_active           BOOLEAN DEFAULT TRUE,
            created_at          {timestamptz} DEFAULT {now},
            updated_at          {timestamptz} DEFAULT {now}
        );
    """)

    # 005 Portal Submissions
    op.execute(f"""
        CREATE TABLE portal_submissions (
            id                      TEXT    PRIMARY KEY DEFAULT {id_default},
            portal_id               TEXT    NOT NULL REFERENCES client_portals(id) ON DELETE CASCADE,
            job_id                  TEXT    NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            submission_token        TEXT    UNIQUE NOT NULL,
            status                  TEXT    NOT NULL DEFAULT 'pending',
            client_feedback         TEXT,
            approved_clip_indices   TEXT,
            expires_at              {timestamptz},
            created_at              {timestamptz} DEFAULT {now},
            updated_at              {timestamptz} DEFAULT {now}
        );
    """)

    # 006 Workspace Audit Logs
    op.execute(f"""
        CREATE TABLE workspace_audit_logs (
            id                  TEXT    PRIMARY KEY DEFAULT {id_default},
            workspace_id        TEXT    NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id             TEXT    REFERENCES users(id) ON DELETE SET NULL,
            action              TEXT    NOT NULL,
            resource_type       TEXT    NOT NULL,
            resource_id         TEXT,
            details_json        TEXT    DEFAULT '{{}}',
            created_at          {timestamptz} DEFAULT {now}
        );
    """)
    op.execute("CREATE INDEX idx_audit_workspace ON workspace_audit_logs(workspace_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_audit_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS portal_submissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS client_portals CASCADE;")
    op.execute("DROP TABLE IF EXISTS workspace_clients CASCADE;")
    op.execute("DROP TABLE IF EXISTS workspace_members CASCADE;")
    op.execute("DROP TABLE IF EXISTS workspaces CASCADE;")
