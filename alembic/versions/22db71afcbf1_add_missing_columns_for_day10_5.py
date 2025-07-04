"""add missing columns for day10_5

Revision ID: 22db71afcbf1
Revises: 
Create Date: 2025-01-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22db71afcbf1'
down_revision: Union[str, None] = 'faa940c31fb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indices column to companies table
    op.add_column('companies', sa.Column('indices', sa.String(255), nullable=True))
    
    # Add event_type column to filings table (for 8-K events)
    op.add_column('filings', sa.Column('event_type', sa.String(100), nullable=True))
    
    # Add comment_count column to filings table
    op.add_column('filings', sa.Column('comment_count', sa.Integer(), nullable=False, server_default='0'))
    
    # Create comments table
    op.create_table('comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filing_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['filing_id'], ['filings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_comments_filing_id'), 'comments', ['filing_id'], unique=False)
    op.create_index(op.f('ix_comments_user_id'), 'comments', ['user_id'], unique=False)
    
    # Create user_votes table to track voting history
    op.create_table('user_votes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filing_id', sa.Integer(), nullable=False),
        sa.Column('vote_type', sa.Enum('bullish', 'neutral', 'bearish', name='votetype'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['filing_id'], ['filings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'filing_id', name='unique_user_filing_vote')
    )
    op.create_index(op.f('ix_user_votes_filing_id'), 'user_votes', ['filing_id'], unique=False)
    op.create_index(op.f('ix_user_votes_user_id'), 'user_votes', ['user_id'], unique=False)
    
    # Update companies indices based on existing boolean columns
    op.execute("""
        UPDATE companies 
        SET indices = CASE 
            WHEN is_sp500 = true AND is_nasdaq100 = true THEN 'S&P 500,NASDAQ 100'
            WHEN is_sp500 = true THEN 'S&P 500'
            WHEN is_nasdaq100 = true THEN 'NASDAQ 100'
            ELSE NULL
        END
    """)
    
    print("✅ Migration completed successfully!")
    print("   - Added 'indices' column to companies table")
    print("   - Added 'event_type' column to filings table")
    print("   - Added 'comment_count' column to filings table")
    print("   - Created 'comments' table")
    print("   - Created 'user_votes' table")
    print("   - Updated companies indices based on existing flags")


def downgrade() -> None:
    # Drop user_votes table
    op.drop_index(op.f('ix_user_votes_user_id'), table_name='user_votes')
    op.drop_index(op.f('ix_user_votes_filing_id'), table_name='user_votes')
    op.drop_table('user_votes')
    
    # Drop comments table
    op.drop_index(op.f('ix_comments_user_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_filing_id'), table_name='comments')
    op.drop_table('comments')
    
    # Remove columns from filings table
    op.drop_column('filings', 'comment_count')
    op.drop_column('filings', 'event_type')
    
    # Remove indices column from companies table
    op.drop_column('companies', 'indices')
    
    # Drop the enum type
    op.execute('DROP TYPE IF EXISTS votetype')