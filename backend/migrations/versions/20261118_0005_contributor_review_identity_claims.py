"""contributor flag evidence, identity claims

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 12:00:00.000000

* ``contributors.flag_evidence_count``: quarantined records that count toward flagging since the
  contributor was last restored, and ``restored_at``. Restoring a contributor resets the count, so a
  restored contributor is flagged again only by new evidence. Backfill: flagged and banned contributors
  keep their quarantined_count; an active contributor at or above the default threshold (5) can only
  have been restored by a moderator, so starts at 0; other active contributors keep their count.
* ``identity_claims``: reports that contradict an established identity (a known GUID under another
  name or class), kept for review instead of applied by a single upload.

Nothing existing is changed or removed; the downgrade drops only what this adds.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contributors', sa.Column('flag_evidence_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('contributors', sa.Column('restored_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE contributors SET flag_evidence_count = CASE "
        "WHEN status = 'active' AND quarantined_count >= 5 THEN 0 ELSE quarantined_count END"
    )
    op.create_table(
        'identity_claims',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('character_id', sa.BigInteger(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('value', sa.String(length=160), nullable=False),
        sa.Column('display_value', sa.String(length=160), nullable=True),
        sa.Column('contributor_id', sa.BigInteger(), nullable=True),
        sa.Column('raw_observation_id', sa.BigInteger(), nullable=True),
        sa.Column('observation_count', sa.Integer(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('resolution_note', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('name','class')", name=op.f('ck_identity_claims_kind')),
        sa.CheckConstraint("status IN ('open','applied','accepted','rejected')", name=op.f('ck_identity_claims_status')),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], name=op.f('fk_identity_claims_character_id_characters'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contributor_id'], ['contributors.id'], name=op.f('fk_identity_claims_contributor_id_contributors'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_observation_id'], ['raw_observations.id'], name=op.f('fk_identity_claims_raw_observation_id_raw_observations'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_identity_claims')),
        sa.UniqueConstraint('character_id', 'kind', 'value', 'contributor_id', name='character_kind_value_contributor'),
    )
    op.create_index(op.f('ix_identity_claims_character_id'), 'identity_claims', ['character_id'], unique=False)
    op.create_index('ix_identity_claims_status', 'identity_claims', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_identity_claims_status', table_name='identity_claims')
    op.drop_index(op.f('ix_identity_claims_character_id'), table_name='identity_claims')
    op.drop_table('identity_claims')
    op.drop_column('contributors', 'restored_at')
    op.drop_column('contributors', 'flag_evidence_count')
