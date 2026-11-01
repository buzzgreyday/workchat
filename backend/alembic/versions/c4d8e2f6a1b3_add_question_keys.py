"""add question keys

Revision ID: c4d8e2f6a1b3
Revises: b7e3d9a1c2f4
Create Date: 2026-11-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f6a1b3'
down_revision: Union[str, Sequence[str], None] = 'b7e3d9a1c2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('question_keys',
    sa.Column('token_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.Uuid(), nullable=False),
    sa.Column('message_hash', sa.String(length=64), nullable=False),
    # server_default because the row is born on the first attempt.
    sa.Column('attempts', sa.Integer(), server_default='1', nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['token_id'], ['tokens.id'], ondelete='RESTRICT'),
    # The race arbiter: one key, one spend, per grant.
    sa.PrimaryKeyConstraint('token_id', 'key'),
    )
    # Purging reads by age.
    op.create_index(op.f('ix_question_keys_created_at'), 'question_keys', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_question_keys_created_at'), table_name='question_keys')
    op.drop_table('question_keys')
