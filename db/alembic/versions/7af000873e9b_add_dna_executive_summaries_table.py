"""Add dna_executive_summaries table

Revision ID: 7af000873e9b
Revises: 86f7cef2ee6c
Create Date: 2026-04-16 16:36:13.614426

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7af000873e9b'
down_revision: Union[str, None] = '86f7cef2ee6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'
    
    # Use TEXT for UUIDs on SQLite, UUID type on Postgres
    id_type = sa.UUID() if is_postgres else sa.String(36)
    now_func = sa.text('now()') if is_postgres else sa.text('CURRENT_TIMESTAMP')

    op.create_table(
        'dna_executive_summaries',
        sa.Column('id', id_type, nullable=False),
        sa.Column('user_id', id_type, nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('context_log_ids', sa.JSON(), nullable=False), # Store as list of UUID strings
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=now_func, nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dna_exec_summaries_user_id', 'dna_executive_summaries', ['user_id'])


def downgrade() -> None:
    op.drop_table('dna_executive_summaries')
