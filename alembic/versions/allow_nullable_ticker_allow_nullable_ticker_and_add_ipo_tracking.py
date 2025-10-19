"""Allow nullable ticker and add IPO tracking fields

Revision ID: allow_nullable_ticker
Revises: e1459d7274d0
Create Date: 2025-08-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'allow_nullable_ticker'
down_revision = 'e1459d7274d0'
branch_labels = None
depends_on = None


def upgrade():
    """
    Make ticker nullable and add IPO tracking fields
    This allows the system to handle S-1 filings from pre-IPO companies
    """
    
    # Step 1: Add new columns for IPO tracking
    op.add_column('companies', 
        sa.Column('has_s1_filing', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column('companies', 
        sa.Column('ipo_date', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Step 2: Alter ticker column to be nullable
    # First drop the unique index (not constraint)
    op.drop_index('ix_companies_ticker', 'companies')
    
    # Then alter the column to be nullable
    op.alter_column('companies', 'ticker',
                    existing_type=sa.String(10),
                    nullable=True)
    
    # Re-create the unique index (NULL values are allowed in unique indexes)
    op.create_index('ix_companies_ticker', 'companies', ['ticker'], unique=True)
    
    # Step 3: Update indices field for existing companies with S-1 filings
    # This is a data migration to mark companies that have S-1 filings
    op.execute("""
        UPDATE companies 
        SET has_s1_filing = true 
        WHERE id IN (
            SELECT DISTINCT company_id 
            FROM filings 
            WHERE filing_type = 'FORM_S1'
        )
    """)
    
    # Step 4: Create an index for better query performance
    op.create_index('idx_companies_has_s1_filing', 'companies', ['has_s1_filing'])
    op.create_index('idx_companies_ipo_date', 'companies', ['ipo_date'])


def downgrade():
    """
    Revert the changes - this may fail if there are NULL tickers in the database
    """
    
    # Drop the new indexes
    op.drop_index('idx_companies_ipo_date', 'companies')
    op.drop_index('idx_companies_has_s1_filing', 'companies')
    
    # Handle NULL tickers before making column non-nullable
    # Generate temporary tickers for companies without them
    op.execute("""
        UPDATE companies 
        SET ticker = 'CIK' || cik 
        WHERE ticker IS NULL
    """)
    
    # Drop and recreate the unique index
    op.drop_index('ix_companies_ticker', 'companies')
    
    # Make ticker non-nullable again
    op.alter_column('companies', 'ticker',
                    existing_type=sa.String(10),
                    nullable=False)
    
    # Recreate the unique index
    op.create_index('ix_companies_ticker', 'companies', ['ticker'], unique=True)
    
    # Drop the new columns
    op.drop_column('companies', 'ipo_date')
    op.drop_column('companies', 'has_s1_filing')