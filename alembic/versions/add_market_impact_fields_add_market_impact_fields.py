"""Add market impact fields for 10-K and 10-Q

Revision ID: add_market_impact_fields
Revises: add_diff_display_fields
Create Date: 2025-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_market_impact_fields'
down_revision: Union[str, None] = 'add_diff_display_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add market_impact_10k and market_impact_10q fields to filings table"""
    
    # Add 10-K market impact field
    op.add_column('filings', 
        sa.Column('market_impact_10k', sa.Text(), nullable=True, 
                  comment='GPT: 10-K potential market impact analysis')
    )
    
    # Add 10-Q market impact field
    op.add_column('filings', 
        sa.Column('market_impact_10q', sa.Text(), nullable=True,
                  comment='GPT: 10-Q potential market impact analysis')
    )
    
    print("✅ Added market_impact_10k and market_impact_10q fields successfully!")


def downgrade() -> None:
    """Remove market_impact_10k and market_impact_10q fields"""
    
    # Drop columns in reverse order
    op.drop_column('filings', 'market_impact_10q')
    op.drop_column('filings', 'market_impact_10k')
    
    print("✅ Removed market impact fields successfully!")