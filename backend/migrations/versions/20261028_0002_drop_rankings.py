"""drop rankings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_participant_metrics_rank', table_name='participant_metrics')
    op.drop_column('participant_metrics', 'rank_eligible')


def downgrade() -> None:
    # Restored values are all false; re-run reconciliation to recompute them.
    op.add_column('participant_metrics', sa.Column('rank_eligible', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.alter_column('participant_metrics', 'rank_eligible', server_default=None)
    op.create_index('ix_participant_metrics_rank', 'participant_metrics', ['metric', 'rank_eligible'], unique=False)
