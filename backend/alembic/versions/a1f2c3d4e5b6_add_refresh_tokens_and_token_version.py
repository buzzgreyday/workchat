"""add refresh tokens and token version

Revision ID: a1f2c3d4e5b6
Revises: 136856bc30c8
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5b6'
down_revision: Union[str, Sequence[str], None] = '136856bc30c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('token_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rotated_to', sa.Uuid(), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['token_id'], ['tokens.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rotated_to'], ['refresh_tokens.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_token_id'), 'refresh_tokens', ['token_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)

    # server_default rather than a backfill: every row that exists today was
    # minted by the v1 flow, and the default has to stay on the column so a
    # future insert that forgets `version` is a v1 grant rather than a null.
    op.add_column('tokens', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('tokens', sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tokens', 'claimed_at')
    op.drop_column('tokens', 'version')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
