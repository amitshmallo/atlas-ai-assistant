"""add usage records table

Revision ID: 52bb938fd5b4
Revises: 7f70e129edb3
Create Date: 2026-07-28 16:13:51.400907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '52bb938fd5b4'
down_revision: Union[str, None] = '7f70e129edb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usage_records',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_oid', sa.String(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usage_records_user_oid'), 'usage_records', ['user_oid'], unique=False)
    op.create_index(op.f('ix_usage_records_created_at'), 'usage_records', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_records_created_at'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_user_oid'), table_name='usage_records')
    op.drop_table('usage_records')
