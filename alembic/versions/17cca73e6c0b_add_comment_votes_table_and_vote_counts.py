"""Add comment votes table and vote counts

Revision ID: 17cca73e6c0b
Revises: e4df702f8ef1
Create Date: 2025-07-12 21:22:34.598850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17cca73e6c0b'
down_revision: Union[str, None] = 'e4df702f8ef1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
