"""add_unified_analysis_fields_for_content_optimization

Revision ID: e1459d7274d0
Revises: add_social_auth_fields
Create Date: 2025-07-30 19:01:24.719608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e1459d7274d0'
down_revision: Union[str, None] = 'add_social_auth_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns for unified analysis
    op.add_column('filings', 
        sa.Column('unified_analysis', sa.Text(), nullable=True, 
                  comment='Unified 800-1200 word narrative analysis')
    )
    
    op.add_column('filings', 
        sa.Column('unified_feed_summary', sa.Text(), nullable=True,
                  comment='One-line feed summary (max 100 chars)')
    )
    
    op.add_column('filings', 
        sa.Column('analysis_version', sa.String(10), nullable=True,
                  comment='Analysis version (v1=legacy, v2=unified)')
    )
    
    op.add_column('filings',
        sa.Column('smart_markup_data', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment='Smart markup metadata for frontend rendering')
    )
    
    op.add_column('filings',
        sa.Column('analyst_expectations', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment='Analyst expectations data for 10-Q')
    )
    
    # Add index for performance
    op.create_index('idx_filings_analysis_version', 'filings', ['analysis_version'])


def downgrade() -> None:
    # Remove index
    op.drop_index('idx_filings_analysis_version', table_name='filings')
    
    # Remove columns
    op.drop_column('filings', 'analyst_expectations')
    op.drop_column('filings', 'smart_markup_data')
    op.drop_column('filings', 'analysis_version')
    op.drop_column('filings', 'unified_feed_summary')
    op.drop_column('filings', 'unified_analysis')