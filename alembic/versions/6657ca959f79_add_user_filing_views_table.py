"""add user filing views table
Revision ID: 6657ca959f79
Revises: 5c0cc3fbd189
Create Date: 2025-07-10 08:23:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6657ca959f79'
down_revision = '5c0cc3fbd189'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_filing_views table to track daily viewing limits
    op.create_table('user_filing_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filing_id', sa.Integer(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), nullable=False),
        sa.Column('view_date', sa.Date(), nullable=False),  # For easy daily counting
        sa.ForeignKeyConstraint(['filing_id'], ['filings.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better query performance
    op.create_index('idx_user_filing_views_user_date', 'user_filing_views', ['user_id', 'view_date'])
    op.create_index('idx_user_filing_views_user_filing', 'user_filing_views', ['user_id', 'filing_id'])
    
    # Add daily_view_count column to users table for caching (optional optimization)
    op.add_column('users', sa.Column('last_view_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('daily_view_count', sa.Integer(), nullable=True, default=0))


def downgrade() -> None:
    # Remove the columns from users table
    op.drop_column('users', 'daily_view_count')
    op.drop_column('users', 'last_view_date')
    
    # Drop indexes
    op.drop_index('idx_user_filing_views_user_filing', table_name='user_filing_views')
    op.drop_index('idx_user_filing_views_user_date', table_name='user_filing_views')
    
    # Drop the table
    op.drop_table('user_filing_views')