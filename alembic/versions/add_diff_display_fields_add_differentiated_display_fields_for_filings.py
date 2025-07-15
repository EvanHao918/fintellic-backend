"""Add differentiated display fields for filings

Revision ID: add_diff_display_fields
Revises: e8aeb514912a
Create Date: 2025-01-15 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_diff_display_fields'
down_revision: Union[str, None] = 'e8aeb514912a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 10-K specific fields
    op.add_column('filings', sa.Column('auditor_opinion', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('three_year_financials', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('business_segments', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('risk_summary', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('growth_drivers', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('management_outlook', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('strategic_adjustments', sa.Text(), nullable=True))
    
    # Add 10-Q specific fields
    op.add_column('filings', sa.Column('expectations_comparison', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('cost_structure', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('guidance_update', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('growth_decline_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('management_tone_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('beat_miss_analysis', sa.Text(), nullable=True))
    
    # Add 8-K specific fields
    op.add_column('filings', sa.Column('item_type', sa.String(length=10), nullable=True))
    op.add_column('filings', sa.Column('items', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('event_timeline', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('event_nature_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('market_impact_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('key_considerations', sa.Text(), nullable=True))
    
    # Add S-1 specific fields
    op.add_column('filings', sa.Column('ipo_details', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('company_overview', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('financial_summary', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('risk_categories', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('filings', sa.Column('growth_path_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('competitive_moat_analysis', sa.Text(), nullable=True))
    
    # Add common fields
    op.add_column('filings', sa.Column('fiscal_year', sa.String(length=10), nullable=True))
    op.add_column('filings', sa.Column('fiscal_quarter', sa.String(length=10), nullable=True))
    op.add_column('filings', sa.Column('period_end_date', sa.DateTime(timezone=True), nullable=True))
    
    # Create indexes for better query performance
    op.create_index(op.f('ix_filings_fiscal_year'), 'filings', ['fiscal_year'], unique=False)
    op.create_index(op.f('ix_filings_fiscal_quarter'), 'filings', ['fiscal_quarter'], unique=False)
    op.create_index(op.f('ix_filings_item_type'), 'filings', ['item_type'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_filings_item_type'), table_name='filings')
    op.drop_index(op.f('ix_filings_fiscal_quarter'), table_name='filings')
    op.drop_index(op.f('ix_filings_fiscal_year'), table_name='filings')
    
    # Drop columns in reverse order
    op.drop_column('filings', 'period_end_date')
    op.drop_column('filings', 'fiscal_quarter')
    op.drop_column('filings', 'fiscal_year')
    
    # Drop S-1 fields
    op.drop_column('filings', 'competitive_moat_analysis')
    op.drop_column('filings', 'growth_path_analysis')
    op.drop_column('filings', 'risk_categories')
    op.drop_column('filings', 'financial_summary')
    op.drop_column('filings', 'company_overview')
    op.drop_column('filings', 'ipo_details')
    
    # Drop 8-K fields
    op.drop_column('filings', 'key_considerations')
    op.drop_column('filings', 'market_impact_analysis')
    op.drop_column('filings', 'event_nature_analysis')
    op.drop_column('filings', 'event_timeline')
    op.drop_column('filings', 'items')
    op.drop_column('filings', 'item_type')
    
    # Drop 10-Q fields
    op.drop_column('filings', 'beat_miss_analysis')
    op.drop_column('filings', 'management_tone_analysis')
    op.drop_column('filings', 'growth_decline_analysis')
    op.drop_column('filings', 'guidance_update')
    op.drop_column('filings', 'cost_structure')
    op.drop_column('filings', 'expectations_comparison')
    
    # Drop 10-K fields
    op.drop_column('filings', 'strategic_adjustments')
    op.drop_column('filings', 'management_outlook')
    op.drop_column('filings', 'growth_drivers')
    op.drop_column('filings', 'risk_summary')
    op.drop_column('filings', 'business_segments')
    op.drop_column('filings', 'three_year_financials')
    op.drop_column('filings', 'auditor_opinion')