"""add guest trials

Revision ID: b7e3d9a1c2f4
Revises: a1f2c3d4e5b6
Create Date: 2026-10-04 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e3d9a1c2f4'
down_revision: Union[str, Sequence[str], None] = 'a1f2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default, as with `version`: every grant that exists today was
    # issued as a link, and an insert that forgets `kind` should be one too.
    op.add_column('tokens', sa.Column('kind', sa.String(length=16), server_default='link', nullable=False))

    op.create_table('trial_requests',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('ip_hash', sa.String(length=64), nullable=False),
    sa.Column('challenge_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    # One trial per address per day; one trial per solved challenge.
    sa.UniqueConstraint('day', 'ip_hash', name='uq_trial_requests_day_ip_hash'),
    sa.UniqueConstraint('challenge_hash'),
    )
    # Purging reads by day.
    op.create_index(op.f('ix_trial_requests_day'), 'trial_requests', ['day'], unique=False)

    op.create_table('trial_budget',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('issued', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('day'),
    )

    # The user every trial grant belongs to. Created here rather than on the
    # first trial, so two first trials arriving together cannot race to insert
    # the same unique name. Not plain "Guest", which a link issued to a company
    # of that name could already hold.
    users = sa.table(
        'users',
        sa.column('id', sa.Uuid()),
        sa.column('name', sa.String()),
    )
    op.bulk_insert(users, [{'id': uuid.uuid4(), 'name': 'Guest (trial)'}])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('trial_budget')
    op.drop_index(op.f('ix_trial_requests_day'), table_name='trial_requests')
    op.drop_table('trial_requests')
    op.drop_column('tokens', 'kind')
    # The trial user stays if any grant still references it (users.id is
    # RESTRICT from tokens); it is a harmless row either way.
    op.execute(
        "DELETE FROM users WHERE name = 'Guest (trial)' "
        "AND NOT EXISTS (SELECT 1 FROM tokens WHERE tokens.user_id = users.id)"
    )
