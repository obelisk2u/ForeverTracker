"""item tooltips

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19 12:00:00.000000

Item tooltips as the addon read them in game (addon 0.2.13 and later), one row per item per
snapshot that carried one. An item shows the version the most installations agree on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('item_tooltip_reports',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('item_key', sa.String(length=160), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('raw_observation_id', sa.BigInteger(), nullable=False),
    sa.Column('contributor_id', sa.BigInteger(), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('lines', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('reported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['contributor_id'], ['contributors.id'], name=op.f('fk_item_tooltip_reports_contributor_id_contributors')),
    sa.ForeignKeyConstraint(['raw_observation_id'], ['raw_observations.id'], name=op.f('fk_item_tooltip_reports_raw_observation_id_raw_observations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_item_tooltip_reports')),
    sa.UniqueConstraint('raw_observation_id', 'item_key', name='raw_observation_item')
    )
    op.create_index('ix_item_tooltip_reports_item_key', 'item_tooltip_reports', ['item_key'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_item_tooltip_reports_item_key', table_name='item_tooltip_reports')
    op.drop_table('item_tooltip_reports')
