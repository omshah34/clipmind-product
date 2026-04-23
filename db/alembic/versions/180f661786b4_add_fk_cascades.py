"""add_fk_cascades

Revision ID: 180f661786b4
Revises: 8c8beb4e1a48
Create Date: 2026-04-23 11:20:20.746997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '180f661786b4'
down_revision: Union[str, None] = '8c8beb4e1a48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'
    
    if not is_postgres:
        return

    # ─── Foreign Key Hardening (Gap 28) ───────────────────────────────────
    # Adding referential integrity with CASCADE/SET NULL rules.
    # Note: SQLite has limited support for adding FKs to existing tables.
    
    # jobs -> users
    op.create_foreign_key('fk_jobs_user_id', 'jobs', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    # jobs -> brand_kits
    op.create_foreign_key('fk_jobs_brand_kit_id', 'jobs', 'brand_kits', ['brand_kit_id'], ['id'], ondelete='SET NULL')
    # jobs -> campaigns
    op.create_foreign_key('fk_jobs_campaign_id', 'jobs', 'campaigns', ['campaign_id'], ['id'], ondelete='SET NULL')
    
    # brand_kits -> users
    op.create_foreign_key('fk_brand_kits_user_id', 'brand_kits', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    # campaigns -> users
    op.create_foreign_key('fk_campaigns_user_id', 'campaigns', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    # connected_sources -> users
    op.create_foreign_key('fk_connected_sources_user_id', 'connected_sources', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    # dna_learning_logs -> users
    op.create_foreign_key('fk_dna_logs_user_id', 'dna_learning_logs', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # dna_executive_summaries -> users
    op.create_foreign_key('fk_dna_exec_summaries_user_id', 'dna_executive_summaries', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('fk_dna_exec_summaries_user_id', 'dna_executive_summaries', type_='foreignkey')
    op.drop_constraint('fk_dna_logs_user_id', 'dna_learning_logs', type_='foreignkey')
    op.drop_constraint('fk_connected_sources_user_id', 'connected_sources', type_='foreignkey')
    op.drop_constraint('fk_campaigns_user_id', 'campaigns', type_='foreignkey')
    op.drop_constraint('fk_brand_kits_user_id', 'brand_kits', type_='foreignkey')
    op.drop_constraint('fk_jobs_campaign_id', 'jobs', type_='foreignkey')
    op.drop_constraint('fk_jobs_brand_kit_id', 'jobs', type_='foreignkey')
    op.drop_constraint('fk_jobs_user_id', 'jobs', type_='foreignkey')
