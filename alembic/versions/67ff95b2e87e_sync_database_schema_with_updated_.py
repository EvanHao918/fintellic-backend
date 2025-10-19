"""Sync database schema with updated models - add new company and filing fields (SAFE VERSION)

Revision ID: 67ff95b2e87e
Revises: allow_nullable_ticker
Create Date: 2025-08-06 02:52:57.604833

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '67ff95b2e87e'
down_revision: Union[str, None] = 'allow_nullable_ticker'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### PHASE 1: Add new columns (safe - no data loss) ###
    
    # Add new columns to companies table
    print("Adding new columns to companies table...")
    op.add_column('companies', sa.Column('sector', sa.String(length=100), nullable=True))
    op.add_column('companies', sa.Column('industry', sa.String(length=100), nullable=True))
    op.add_column('companies', sa.Column('headquarters', sa.String(length=100), nullable=True))
    op.add_column('companies', sa.Column('country', sa.String(length=50), server_default='United States', nullable=True))
    op.add_column('companies', sa.Column('founded_year', sa.Integer(), nullable=True))
    op.add_column('companies', sa.Column('employees', sa.Integer(), nullable=True))
    op.add_column('companies', sa.Column('market_cap', sa.Float(), nullable=True))
    op.add_column('companies', sa.Column('website', sa.String(length=255), nullable=True))
    # Add is_public column with proper handling for existing data
    # First add as nullable with default
    op.add_column('companies', sa.Column('is_public', sa.Boolean(), nullable=True))
    
    # Update existing rows to have is_public = true
    op.execute("UPDATE companies SET is_public = true WHERE is_public IS NULL")
    
    # Now make it NOT NULL
    op.alter_column('companies', 'is_public',
                    existing_type=sa.Boolean(),
                    nullable=False,
                    server_default='true')
    
    # Skip CIK column type change - keep it as VARCHAR(20) for safety
    # We can change this later if needed after verifying all CIK values
    print("Skipping CIK column type change for safety...")
    
    # Add new columns to filings table
    print("Adding new columns to filings table...")
    op.add_column('filings', sa.Column('ticker', sa.String(length=10), nullable=True))
    op.add_column('filings', sa.Column('form_type', sa.String(length=20), nullable=True))
    op.add_column('filings', sa.Column('accepted_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('filings', sa.Column('filing_url', sa.String(length=500), nullable=True))
    op.add_column('filings', sa.Column('primary_document_url', sa.String(length=500), nullable=True))
    op.add_column('filings', sa.Column('interactive_data_url', sa.String(length=500), nullable=True))
    op.add_column('filings', sa.Column('retry_count', sa.Integer(), server_default='0', nullable=True))
    
    # Processing timestamps
    op.add_column('filings', sa.Column('download_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('filings', sa.Column('parsing_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('filings', sa.Column('analysis_completed_at', sa.DateTime(timezone=True), nullable=True))
    
    # Content storage
    op.add_column('filings', sa.Column('raw_text', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('raw_text_size', sa.Integer(), nullable=True))
    op.add_column('filings', sa.Column('primary_doc_html', sa.Text(), nullable=True))
    
    # JSON fields for structured data
    op.add_column('filings', sa.Column('extracted_sections', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('table_of_contents', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('financial_data', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('financial_metrics', sa.JSON(), nullable=True))
    
    # Financial metrics
    op.add_column('filings', sa.Column('revenue', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('net_income', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('eps', sa.Float(), nullable=True))
    
    # Analyst expectations (for 10-Q)
    op.add_column('filings', sa.Column('expected_eps', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('expected_revenue', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('eps_surprise', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('revenue_surprise', sa.Float(), nullable=True))
    
    # Event information (for 8-K)
    op.add_column('filings', sa.Column('event_items', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('event_description', sa.Text(), nullable=True))
    
    # IPO specific (for S-1)
    op.add_column('filings', sa.Column('ipo_price_range_low', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('ipo_price_range_high', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('ipo_shares_offered', sa.Integer(), nullable=True))
    op.add_column('filings', sa.Column('ipo_use_of_proceeds', sa.Text(), nullable=True))
    
    # AI Analysis results
    op.add_column('filings', sa.Column('unified_score', sa.Integer(), nullable=True))
    op.add_column('filings', sa.Column('key_points', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('risks', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('opportunities', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('sentiment_score', sa.Float(), nullable=True))
    op.add_column('filings', sa.Column('market_reaction_prediction', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('competitive_positioning', sa.Text(), nullable=True))
    
    # Filing-specific analysis fields
    # 10-K specific
    op.add_column('filings', sa.Column('annual_business_overview', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('annual_strategy_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('annual_risk_assessment', sa.JSON(), nullable=True))
    
    # 10-Q specific
    op.add_column('filings', sa.Column('quarterly_performance', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('quarterly_guidance', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('quarterly_vs_expectations', sa.JSON(), nullable=True))
    
    # 8-K specific
    op.add_column('filings', sa.Column('event_significance', sa.String(length=50), nullable=True))
    op.add_column('filings', sa.Column('event_impact_analysis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('required_actions', sa.JSON(), nullable=True))
    
    # S-1 specific
    op.add_column('filings', sa.Column('ipo_company_overview', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('ipo_investment_thesis', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('ipo_risk_factors', sa.JSON(), nullable=True))
    op.add_column('filings', sa.Column('ipo_valuation_analysis', sa.Text(), nullable=True))
    
    # Summaries
    op.add_column('filings', sa.Column('executive_summary', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('technical_summary', sa.Text(), nullable=True))
    op.add_column('filings', sa.Column('retail_summary', sa.Text(), nullable=True))
    
    # Metadata
    op.add_column('filings', sa.Column('word_count', sa.Integer(), nullable=True))
    op.add_column('filings', sa.Column('reading_time_minutes', sa.Integer(), nullable=True))
    op.add_column('filings', sa.Column('complexity_score', sa.Float(), nullable=True))
    
    # Data quality
    op.add_column('filings', sa.Column('has_financial_statements', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('filings', sa.Column('has_md_a', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('filings', sa.Column('has_risk_factors', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('filings', sa.Column('data_quality_score', sa.Float(), nullable=True))
    
    # Cache control
    op.add_column('filings', sa.Column('cache_key', sa.String(length=100), nullable=True))
    op.add_column('filings', sa.Column('cache_expires_at', sa.DateTime(timezone=True), nullable=True))
    
    # ### PHASE 2: Add new indexes (safe) ###
    print("Adding new indexes...")
    op.create_index(op.f('ix_filings_status'), 'filings', ['status'], unique=False)
    op.create_index(op.f('ix_filings_ticker'), 'filings', ['ticker'], unique=False)
    
    # ### PHASE 3: Handle comment reply columns carefully ###
    # Check if there's data in these columns before dropping
    connection = op.get_bind()
    result = connection.execute(sa.text(
        "SELECT COUNT(*) FROM comments WHERE reply_to_comment_id IS NOT NULL OR reply_to_user_id IS NOT NULL"
    ))
    reply_count = result.scalar()
    
    if reply_count > 0:
        print(f"WARNING: Found {reply_count} comments with replies. Skipping deletion of reply columns.")
        print("You may want to migrate this data before removing these columns.")
    else:
        print("No reply data found, safe to remove reply columns...")
        op.drop_index('ix_comments_reply_to_comment_id', table_name='comments')
        op.drop_constraint('fk_comments_reply_to_user_id_users', 'comments', type_='foreignkey')
        op.drop_constraint('fk_comments_reply_to_comment_id_comments', 'comments', type_='foreignkey')
        op.drop_column('comments', 'reply_to_comment_id')
        op.drop_column('comments', 'reply_to_user_id')
    
    # ### PHASE 4: Handle old columns carefully ###
    print("\n=== Old Columns Status ===")
    print("The following old columns exist but are not in the current model:")
    print("They will be kept for now to preserve data. You can drop them later after data migration.")
    
    old_columns = [
        'analyst_expectations', 'key_questions', 'fiscal_year', 'fiscal_quarter',
        'primary_doc_url', 'cost_structure', 'bearish_votes', 'bullish_votes', 
        'neutral_votes', 'chart_data', 'management_outlook', 'tone_explanation',
        'ipo_details', 'filing_specific_data', 'full_text_url', 'ai_summary',
        'three_year_financials', 'key_considerations', 'key_quotes', 
        'smart_markup_data', 'strategic_adjustments', 'items',
        'expectations_comparison', 'risk_categories', 'auditor_opinion',
        'risk_summary', 'event_timeline', 'item_type', 'comment_count',
        'is_amended', 'guidance_update', 'market_impact_10q', 'market_impact_10k',
        'key_tags', 'beat_miss_analysis', 'event_nature_analysis',
        'business_segments', 'growth_decline_analysis', 'growth_drivers',
        'period_date', 'primary_doc_description', 'company_overview',
        'market_impact_analysis', 'financial_summary', 'financial_highlights',
        'management_tone_analysis', 'growth_path_analysis', 'competitive_moat_analysis'
    ]
    
    print(f"Total: {len(old_columns)} columns")
    print("\nTo drop these columns later, run:")
    print("python manage_old_columns.py --action=drop")
    
    print("\n✅ Migration completed successfully!")


def downgrade() -> None:
    # Reverse of upgrade operations
    print("Rolling back migration...")
    
    # Drop new indexes
    op.drop_index(op.f('ix_filings_ticker'), table_name='filings')
    op.drop_index(op.f('ix_filings_status'), table_name='filings')
    
    # Drop all new columns from filings table
    new_filing_columns = [
        'cache_expires_at', 'cache_key', 'data_quality_score', 'has_risk_factors',
        'has_md_a', 'has_financial_statements', 'complexity_score', 'reading_time_minutes',
        'word_count', 'retail_summary', 'technical_summary', 'executive_summary',
        'ipo_valuation_analysis', 'ipo_risk_factors', 'ipo_investment_thesis',
        'ipo_company_overview', 'required_actions', 'event_impact_analysis',
        'event_significance', 'quarterly_vs_expectations', 'quarterly_guidance',
        'quarterly_performance', 'annual_risk_assessment', 'annual_strategy_analysis',
        'annual_business_overview', 'competitive_positioning', 'market_reaction_prediction',
        'sentiment_score', 'opportunities', 'risks', 'key_points', 'unified_score',
        'ipo_use_of_proceeds', 'ipo_shares_offered', 'ipo_price_range_high',
        'ipo_price_range_low', 'event_description', 'event_items', 'revenue_surprise',
        'eps_surprise', 'expected_revenue', 'expected_eps', 'eps', 'net_income',
        'revenue', 'financial_metrics', 'financial_data', 'table_of_contents',
        'extracted_sections', 'primary_doc_html', 'raw_text_size', 'raw_text',
        'analysis_completed_at', 'parsing_completed_at', 'download_completed_at',
        'retry_count', 'interactive_data_url', 'primary_document_url', 'filing_url',
        'accepted_date', 'form_type', 'ticker'
    ]
    
    for column in new_filing_columns:
        op.drop_column('filings', column)
    
    # Drop new columns from companies table
    new_company_columns = [
        'is_public', 'website', 'market_cap', 'employees', 'founded_year',
        'country', 'headquarters', 'industry', 'sector'
    ]
    
    for column in new_company_columns:
        op.drop_column('companies', column)
    
    # Restore comment reply columns if they were dropped
    op.add_column('comments', sa.Column('reply_to_user_id', sa.INTEGER(), nullable=True))
    op.add_column('comments', sa.Column('reply_to_comment_id', sa.INTEGER(), nullable=True))
    op.create_foreign_key('fk_comments_reply_to_comment_id_comments', 'comments', 'comments', 
                          ['reply_to_comment_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_comments_reply_to_user_id_users', 'comments', 'users', 
                          ['reply_to_user_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_comments_reply_to_comment_id', 'comments', ['reply_to_comment_id'], unique=False)
    
    print("✅ Rollback completed!")