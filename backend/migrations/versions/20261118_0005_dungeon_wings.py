"""dungeon wings

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 12:00:00.000000

A dungeon whose wings share one instance map ID (Scarlet Monastery) gets one row per wing beside the
row for the whole dungeon: ``wing`` is empty for the whole dungeon, so every existing row keeps its
meaning. Runs move to their wing's row when they are rebuilt (python -m app.cli rebuild).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dungeons', sa.Column('wing', sa.String(length=40), server_default='', nullable=False))
    # Named after its first column by the naming convention, like the constraint it replaces.
    op.drop_constraint(op.f('uq_dungeons_map_id'), 'dungeons', type_='unique')
    op.create_unique_constraint(op.f('uq_dungeons_map_id'), 'dungeons', ['map_id', 'wing'])


def downgrade() -> None:
    # Runs in a wing go back to the whole dungeon, and the wing rows are removed.
    op.execute(
        "UPDATE dungeon_runs r SET dungeon_id = base.id FROM dungeons w, dungeons base "
        "WHERE r.dungeon_id = w.id AND w.wing <> '' AND base.map_id = w.map_id AND base.wing = ''"
    )
    op.execute("DELETE FROM dungeons WHERE wing <> ''")
    op.drop_constraint(op.f('uq_dungeons_map_id'), 'dungeons', type_='unique')
    op.create_unique_constraint(op.f('uq_dungeons_map_id'), 'dungeons', ['map_id'])
    op.drop_column('dungeons', 'wing')
