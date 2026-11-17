"""reported completion

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "reported": the recording player marked the run as completed in the addon (0.2.10), with no
    # completion event and no known final boss killed.
    op.drop_constraint(op.f('ck_dungeon_runs_completion_confidence'), 'dungeon_runs', type_='check')
    op.create_check_constraint(
        op.f('ck_dungeon_runs_completion_confidence'),
        'dungeon_runs',
        "completion_confidence IN ('verified','probable','reported','none')",
    )


def downgrade() -> None:
    op.execute("UPDATE dungeon_runs SET outcome = 'unknown', completion_confidence = 'none' WHERE completion_confidence = 'reported'")
    op.drop_constraint(op.f('ck_dungeon_runs_completion_confidence'), 'dungeon_runs', type_='check')
    op.create_check_constraint(
        op.f('ck_dungeon_runs_completion_confidence'),
        'dungeon_runs',
        "completion_confidence IN ('verified','probable','none')",
    )
