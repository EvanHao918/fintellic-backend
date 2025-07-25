"""convert json fields to text for ai narrative

Revision ID: 163e6310541c
Revises: add_diff_display_fields
Create Date: 2025-01-24 15:48:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '163e6310541c'
down_revision: Union[str, None] = 'add_diff_display_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert JSON fields to Text for narrative content"""
    
    # 10-K fields
    op.alter_column('filings', 'three_year_financials',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'business_segments',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'risk_summary',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    # 10-Q fields
    op.alter_column('filings', 'expectations_comparison',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'cost_structure',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'guidance_update',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    # 8-K fields
    op.alter_column('filings', 'items',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'event_timeline',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    # S-1 fields
    op.alter_column('filings', 'ipo_details',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'financial_summary',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)
    
    op.alter_column('filings', 'risk_categories',
                    existing_type=postgresql.JSON(astext_type=sa.Text()),
                    type_=sa.Text(),
                    existing_nullable=True)


def downgrade() -> None:
    """Revert Text fields back to JSON"""
    
    # S-1 fields
    op.alter_column('filings', 'risk_categories',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'financial_summary',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'ipo_details',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    # 8-K fields
    op.alter_column('filings', 'event_timeline',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'items',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    # 10-Q fields
    op.alter_column('filings', 'guidance_update',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'cost_structure',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'expectations_comparison',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    # 10-K fields
    op.alter_column('filings', 'risk_summary',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'business_segments',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
    
    op.alter_column('filings', 'three_year_financials',
                    existing_type=sa.Text(),
                    type_=postgresql.JSON(astext_type=sa.Text()),
                    existing_nullable=True)
