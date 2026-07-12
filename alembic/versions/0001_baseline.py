"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-07-12

"""
from typing import Sequence, Union

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No tables yet — Phase 1 only proves the migration pipeline works end to end.
    pass


def downgrade() -> None:
    pass
