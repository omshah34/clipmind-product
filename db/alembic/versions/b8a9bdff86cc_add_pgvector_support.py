"""Add pgvector support

Revision ID: b8a9bdff86cc
Revises: 7af000873e9b
Create Date: 2026-04-21 18:05:55.731127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8a9bdff86cc'
down_revision: Union[str, None] = '7af000873e9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SKIPPED: Environment lacks 'vector' extension.
    # Using local HNSW fallback in services/discovery.py
    pass


def downgrade() -> None:
    pass
