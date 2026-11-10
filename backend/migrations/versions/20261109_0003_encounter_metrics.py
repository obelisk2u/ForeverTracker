"""encounter metrics

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per boss attempt: each character's damage-meter totals for that fight. Existing runs get
    # them when reconciliation runs again (python -m app.cli rebuild).
    op.add_column('run_encounters', sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.alter_column('run_encounters', 'metrics', server_default=None)
    op.add_column('run_encounters', sa.Column('metrics_status', sa.String(length=16), nullable=True))
    op.add_column('run_encounters', sa.Column('combat_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('run_encounters', 'combat_seconds')
    op.drop_column('run_encounters', 'metrics_status')
    op.drop_column('run_encounters', 'metrics')
