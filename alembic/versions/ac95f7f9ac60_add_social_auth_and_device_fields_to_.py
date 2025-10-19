"""Add social auth and device fields to users table

Revision ID: add_social_auth_fields
Revises: [previous_revision]
Create Date: 2025-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_social_auth_fields'
down_revision = '163e6310541c'  # 你当前的版本
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add social authentication and device tracking fields to users table"""
    
    # 添加社交登录相关字段
    op.add_column('users', sa.Column('avatar_url', sa.String(512), nullable=True))
    op.add_column('users', sa.Column('apple_user_id', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('google_user_id', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('linkedin_user_id', sa.String(255), nullable=True))
    
    # 添加登录追踪字段
    op.add_column('users', sa.Column('last_login_ip', sa.String(45), nullable=True))
    op.add_column('users', sa.Column('registration_source', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('registration_device_type', sa.String(50), nullable=True))
    
    # 添加设备相关字段
    op.add_column('users', sa.Column('biometric_settings', sa.String(512), nullable=True))
    op.add_column('users', sa.Column('device_tokens', sa.String(2048), nullable=True))
    
    # 修改 hashed_password 为可空（支持纯社交登录）
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.String(255),
                    nullable=True)
    
    # 创建唯一索引
    op.create_index('ix_users_apple_user_id', 'users', ['apple_user_id'], unique=True)
    op.create_index('ix_users_google_user_id', 'users', ['google_user_id'], unique=True)
    op.create_index('ix_users_linkedin_user_id', 'users', ['linkedin_user_id'], unique=True)


def downgrade() -> None:
    """Remove social authentication and device tracking fields from users table"""
    
    # 删除索引
    op.drop_index('ix_users_linkedin_user_id', table_name='users')
    op.drop_index('ix_users_google_user_id', table_name='users')
    op.drop_index('ix_users_apple_user_id', table_name='users')
    
    # 恢复 hashed_password 为非空
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.String(255),
                    nullable=False)
    
    # 删除列
    op.drop_column('users', 'device_tokens')
    op.drop_column('users', 'biometric_settings')
    op.drop_column('users', 'registration_device_type')
    op.drop_column('users', 'registration_source')
    op.drop_column('users', 'last_login_ip')
    op.drop_column('users', 'linkedin_user_id')
    op.drop_column('users', 'google_user_id')
    op.drop_column('users', 'apple_user_id')
    op.drop_column('users', 'avatar_url')