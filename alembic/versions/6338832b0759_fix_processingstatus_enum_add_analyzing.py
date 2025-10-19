"""fix_processingstatus_enum_add_analyzing

Revision ID: 6338832b0759
Revises: 67ff95b2e87e
Create Date: 2025-08-06 12:51:31.060080

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '[自动生成的ID]'  # 保留自动生成的ID
down_revision = '67ff95b2e87e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing enum values to processingstatus"""
    # PostgreSQL allows adding new enum values
    # Add 'analyzing' if it doesn't exist
    with op.get_context().autocommit_block():
        # First, let's add the missing lowercase values that model expects
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'pending'")
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'downloading'")
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'parsing'")
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'analyzing'")  # The missing value!
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'completed'")
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'failed'")
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'skipped'")


def downgrade() -> None:
    """Note: Removing enum values in PostgreSQL is complex and usually not needed"""
    # We'll just update any 'analyzing' status back to 'parsing'
    op.execute("UPDATE filings SET status = 'parsing' WHERE status = 'analyzing'")
    pass