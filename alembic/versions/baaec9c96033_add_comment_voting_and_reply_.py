"""Add comment voting and reply functionality

Revision ID: baaec9c96033
Revises: 17cca73e6c0b
Create Date: 2025-07-13 15:53:05.746277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'baaec9c96033'
down_revision: Union[str, None] = '17cca73e6c0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('comment_votes', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('comment_votes', 'vote_type',
                existing_type=sa.VARCHAR(length=10),
                type_=sa.Integer(),
                existing_nullable=False,
                postgresql_using='CASE WHEN vote_type = \'bullish\' THEN 1 WHEN vote_type = \'bearish\' THEN -1 ELSE 0 END')
    op.drop_constraint('comment_votes_user_id_comment_id_key', 'comment_votes', type_='unique')
    op.drop_index('ix_comment_votes_comment_id', table_name='comment_votes')
    op.drop_index('ix_comment_votes_user_id', table_name='comment_votes')
    op.create_index(op.f('ix_comment_votes_id'), 'comment_votes', ['id'], unique=False)
    op.create_unique_constraint('unique_user_comment_vote', 'comment_votes', ['user_id', 'comment_id'])
    op.add_column('comments', sa.Column('reply_to_comment_id', sa.Integer(), nullable=True))
    op.add_column('comments', sa.Column('reply_to_user_id', sa.Integer(), nullable=True))
    op.add_column('comments', sa.Column('upvotes', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('comments', sa.Column('downvotes', sa.Integer(), nullable=False, server_default='0'))
    op.create_index(op.f('ix_comments_id'), 'comments', ['id'], unique=False)
    op.create_index(op.f('ix_comments_reply_to_comment_id'), 'comments', ['reply_to_comment_id'], unique=False)
    op.create_foreign_key(op.f('fk_comments_reply_to_user_id_users'), 'comments', 'users', ['reply_to_user_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_comments_reply_to_comment_id_comments'), 'comments', 'comments', ['reply_to_comment_id'], ['id'], ondelete='SET NULL')
    op.drop_column('comments', 'dislikes_count')
    op.drop_column('comments', 'likes_count')
    op.create_index(op.f('ix_earnings_calendar_id'), 'earnings_calendar', ['id'], unique=False)
    op.drop_index('idx_user_filing_views_user_date', table_name='user_filing_views')
    op.drop_index('idx_user_filing_views_user_filing', table_name='user_filing_views')
    op.create_index(op.f('ix_user_filing_views_id'), 'user_filing_views', ['id'], unique=False)
    op.create_index(op.f('ix_user_votes_id'), 'user_votes', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_user_votes_id'), table_name='user_votes')
    op.drop_index(op.f('ix_user_filing_views_id'), table_name='user_filing_views')
    op.create_index('idx_user_filing_views_user_filing', 'user_filing_views', ['user_id', 'filing_id'], unique=False)
    op.create_index('idx_user_filing_views_user_date', 'user_filing_views', ['user_id', 'view_date'], unique=False)
    op.drop_index(op.f('ix_earnings_calendar_id'), table_name='earnings_calendar')
    op.add_column('comments', sa.Column('likes_count', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False))
    op.add_column('comments', sa.Column('dislikes_count', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False))
    op.drop_constraint(op.f('fk_comments_reply_to_comment_id_comments'), 'comments', type_='foreignkey')
    op.drop_constraint(op.f('fk_comments_reply_to_user_id_users'), 'comments', type_='foreignkey')
    op.drop_index(op.f('ix_comments_reply_to_comment_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_id'), table_name='comments')
    op.drop_column('comments', 'downvotes')
    op.drop_column('comments', 'upvotes')
    op.drop_column('comments', 'reply_to_user_id')
    op.drop_column('comments', 'reply_to_comment_id')
    op.drop_constraint('unique_user_comment_vote', 'comment_votes', type_='unique')
    op.drop_index(op.f('ix_comment_votes_id'), table_name='comment_votes')
    op.create_index('ix_comment_votes_user_id', 'comment_votes', ['user_id'], unique=False)
    op.create_index('ix_comment_votes_comment_id', 'comment_votes', ['comment_id'], unique=False)
    op.create_unique_constraint('comment_votes_user_id_comment_id_key', 'comment_votes', ['user_id', 'comment_id'])
    op.alter_column('comment_votes', 'vote_type',
               existing_type=sa.Integer(),
               type_=sa.VARCHAR(length=10),
               existing_nullable=False)
    op.drop_column('comment_votes', 'updated_at')
    # ### end Alembic commands ###