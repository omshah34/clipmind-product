"""Gap 83: Add composite index on integrations(user_id, integration_type).

The single-column index on user_id exists but token lookups that also filter
by integration_type require a covering composite index to avoid a full table
scan on the user's rows.

Gap 90: Standardize datetime handling in jobs (updated_at default).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "3a5b8c1d2e4f"
down_revision = "180f661786b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Gap 83: Composite covering index for fast token lookups by (user_id, type)
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_integrations_user_type
            ON integrations (user_id, integration_type);
            """
        )
        # Also add an index on the token manager query path
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_integrations_active
            ON integrations (user_id, is_active)
            WHERE is_active = TRUE;
            """
        )
    else:
        # SQLite: regular non-concurrent index
        integrations_exists = bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='integrations'"
        ).fetchone()
        if not integrations_exists:
            return
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_integrations_user_type "
            "ON integrations (user_id, integration_type)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_integrations_user_type")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_integrations_active")
    else:
        op.execute("DROP INDEX IF EXISTS idx_integrations_user_type")
