# app/services/ai_processor.py
"""
AI Processor Service - Enhanced with Flash Note Style for o3-mini
Version: v12_unified_markup
MAJOR UPDATE: 
- Switched to o3-mini reasoning model
- Restructured 10-Q prompt with Sell-Side Flash Note style
- Enhanced beat/miss calculation workflow to prevent AI失焦
- Optimized for autonomous web search and tool use
- NEW v11: Role-driven concise summaries (120-180 chars)
- NEW v11: Pure role definition without artificial examples
- NEW v12: Unified visual markup system across all filing types
  * Removed emoji from all analysis outputs
  * Three inline emphasis types: **highlight**, __bold__, *italic*
  * Consistent ## subheader format
  * Professional appearance without emoji clutter
"""
import json
import re
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
import logging
from pathlib import Path
import asyncio
import tiktoken

from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.filing import Filing, ProcessingStatus, FilingType
from app.core.config import settings
from app.services.text_extractor import text_extractor
from app.services.fmp_service import fmp_service
from app.core.cache import cache

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Enhanced data source marking patterns with web search citations
DATA_SOURCE_PATTERNS = {
    'document': r'\[DOC:\s*([^\]]+)\]',
    'search': r'\[(\d+)\]',
    'calc': r'\[CALC:\s*([^\]]+)\]',
    'fmp': r'\[FMP\]',
    'no_data': r'\[NO_DATA\]',
    'caution': r'\[CAUTION\]'
}

# Universal writing guidelines for feed summaries
FEED_SUMMARY_GUIDELINES = """
ROLE: You're writing a mobile push notification for retail investors who just got alerted.

CORE PRINCIPLES:
- Count in WORDS, not characters
- Start with ticker symbol (e.g., "TSLA reports..." or "AAPL beats...")
- Present tense, active voice
- Clean number formats: "$5.5B" not "$5.524B", "23%" not "23.4%"
- Beat/miss without exact amounts: "beats estimates" not "beats by $0.25B"
- Focus on substance over buzzwords

TONE: Professional, concise, factual - like a Bloomberg terminal alert.

AVOID: Buzzwords ("strategic", "positioned", "innovative"), formal phrases ("announced that"), exact beat/miss amounts, unnecessary details.
"""

# SEC Official Item Definitions - Authoritative reference for 8-K classification
SEC_ITEM_DEFINITIONS = {
    '1.01': {
        'title': 'Entry into a Material Definitive Agreement',
        'category': 'Material Agreement',
        'description': 'Material agreements such as contracts, partnerships, or licensing deals',
        'focus_areas': ['parties involved', 'key commercial terms', 'financial impact', 'duration and termination'],
        'suggested_tags': ['Material Agreement']
    },
    '1.02': {
        'title': 'Termination of a Material Definitive Agreement',
        'category': 'Agreement Termination',
        'description': 'Termination or material modification of agreements',
        'focus_areas': ['agreement being terminated', 'reason for termination', 'financial impact', 'effective date'],
        'suggested_tags': ['Agreement Termination']
    },
    '1.03': {
        'title': 'Bankruptcy or Receivership',
        'category': 'Bankruptcy',
        'description': 'Bankruptcy filings or receivership proceedings',
        'focus_areas': ['type of proceeding', 'court', 'debts', 'restructuring plans'],
        'suggested_tags': ['Bankruptcy', 'Financial Distress']
    },
    '2.01': {
        'title': 'Completion of Acquisition or Disposition of Assets',
        'category': 'M&A Transaction',
        'description': 'Mergers, acquisitions, or asset sales',
        'focus_areas': ['target or buyer', 'transaction value', 'deal structure', 'closing date', 'strategic rationale'],
        'suggested_tags': ['M&A Deal', 'Acquisition']
    },
    '2.02': {
        'title': 'Results of Operations and Financial Condition',
        'category': 'Earnings Release',
        'description': 'Quarterly or annual financial results announcement',
        'focus_areas': ['revenue', 'EPS', 'net income', 'margins', 'guidance'],
        'suggested_tags': ['Earnings Release']
    },
    '2.03': {
        'title': 'Creation of a Direct Financial Obligation',
        'category': 'Financing Event',
        'description': 'New debt issuance, credit facilities, loans, or commercial paper programs',
        'focus_areas': ['amount', 'maturity', 'interest rate', 'purpose of proceeds', 'covenants'],
        'suggested_tags': ['Financing', 'Debt Issuance']
    },
    '2.04': {
        'title': 'Triggering Events That Accelerate or Increase Obligations',
        'category': 'Debt Acceleration',
        'description': 'Events triggering debt acceleration or default',
        'focus_areas': ['triggering event', 'obligations affected', 'amounts', 'consequences'],
        'suggested_tags': ['Debt Default', 'Financial Distress']
    },
    '2.05': {
        'title': 'Costs Associated with Exit or Disposal Activities',
        'category': 'Restructuring',
        'description': 'Restructuring charges, facility closures, or workforce reductions',
        'focus_areas': ['nature of restructuring', 'charges amount', 'affected operations', 'timing', 'expected savings'],
        'suggested_tags': ['Restructuring', 'Cost Reduction']
    },
    '2.06': {
        'title': 'Material Impairments',
        'category': 'Impairment Charge',
        'description': 'Material impairment charges on assets or goodwill',
        'focus_areas': ['assets impaired', 'impairment amount', 'reason', 'impact on earnings'],
        'suggested_tags': ['Impairment', 'Asset Write-Down']
    },
    '3.01': {
        'title': 'Notice of Delisting or Failure to Satisfy Listing Rule',
        'category': 'Delisting Risk',
        'description': 'Notice of delisting or non-compliance with exchange rules',
        'focus_areas': ['exchange', 'rule violated', 'company response', 'timeline'],
        'suggested_tags': ['Delisting Risk', 'Compliance']
    },
    '3.02': {
        'title': 'Unregistered Sales of Equity Securities',
        'category': 'Private Placement',
        'description': 'Private placement or unregistered securities sales',
        'focus_areas': ['securities sold', 'purchasers', 'consideration', 'exemption relied upon'],
        'suggested_tags': ['Private Placement', 'Equity Issuance']
    },
    '4.01': {
        'title': 'Changes in Registrant\'s Certifying Accountant',
        'category': 'Auditor Change',
        'description': 'Change in independent auditor',
        'focus_areas': ['former auditor', 'new auditor', 'reason for change', 'disagreements'],
        'suggested_tags': ['Auditor Change']
    },
    '4.02': {
        'title': 'Non-Reliance on Previously Issued Financial Statements',
        'category': 'Restatement',
        'description': 'Financial restatement or non-reliance on prior statements',
        'focus_areas': ['periods affected', 'nature of errors', 'financial impact', 'restatement timeline'],
        'suggested_tags': ['Restatement', 'Accounting Issue']
    },
    '5.01': {
        'title': 'Changes in Control of Registrant',
        'category': 'Change of Control',
        'description': 'Change in control of the company',
        'focus_areas': ['new controlling party', 'transaction structure', 'terms', 'management changes'],
        'suggested_tags': ['Change of Control', 'Ownership Change']
    },
    '5.02': {
        'title': 'Departure of Directors or Certain Officers; Election of Directors',
        'category': 'Executive/Board Change',
        'description': 'Changes in executive officers or board of directors',
        'focus_areas': ['name and position', 'effective date', 'reason (if departure)', 'successor details', 'background'],
        'suggested_tags': ['Executive Change', 'Board Change']
    },
    '5.03': {
        'title': 'Amendments to Articles of Incorporation or Bylaws',
        'category': 'Governance Change',
        'description': 'Changes to corporate governance documents',
        'focus_areas': ['nature of amendment', 'effective date', 'reason', 'shareholder impact'],
        'suggested_tags': ['Governance Change']
    },
    '5.07': {
        'title': 'Submission of Matters to a Vote of Security Holders',
        'category': 'Shareholder Vote',
        'description': 'Results of shareholder meetings and votes',
        'focus_areas': ['matters voted on', 'vote results', 'outcome', 'next steps'],
        'suggested_tags': ['Shareholder Vote', 'Annual Meeting']
    },
    '7.01': {
        'title': 'Regulation FD Disclosure',
        'category': 'Reg FD Disclosure',
        'description': 'Public disclosure under Regulation Fair Disclosure',
        'focus_areas': ['information disclosed', 'context', 'significance'],
        'suggested_tags': ['Reg FD Disclosure']
    },
    '8.01': {
        'title': 'Other Events',
        'category': 'Other Corporate Event',
        'description': 'Material events not covered by other Item categories',
        'focus_areas': ['nature of event', 'parties involved', 'significance', 'next steps'],
        'suggested_tags': ['Corporate Event']
    },
    '9.01': {
        'title': 'Financial Statements and Exhibits',
        'category': 'Exhibits',
        'description': 'Financial statements and exhibits filed with the 8-K (supporting documents)',
        'focus_areas': ['exhibits listed'],
        'suggested_tags': []  # Usually accompanies other items
    }
}


class AIProcessor:
    """
    Process filings using OpenAI o3-mini with Flash Note structure
    v10_flash_note_o3mini: Optimized for reasoning model with analyst estimates integration
    """
    
    def __init__(self):
        self.model = settings.AI_MODEL  # Now using o3-mini
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        self.enable_web_search = settings.WEB_SEARCH_ENABLED
        
        self.encoding = self._initialize_tokenizer()
        
        # GPT-4.1 supports 1M context window, set generous limit
        # This ensures large filings (e.g., ORCL 3.77MB iXBRL) are not truncated
        self.max_input_tokens = 500000
        self.target_output_tokens = 4000
    
    def _initialize_tokenizer(self):
        """Robust tokenizer initialization with graceful fallbacks"""
        try:
            logger.info("Initializing tiktoken with cl100k_base encoding")
            encoding = tiktoken.get_encoding("cl100k_base")
            logger.info("✅ Successfully initialized tiktoken with cl100k_base")
            return encoding
            
        except Exception as e1:
            logger.warning(f"Failed to load cl100k_base encoding: {e1}")
            
            try:
                logger.info("Attempting tiktoken with o200k_base encoding")
                encoding = tiktoken.get_encoding("o200k_base")
                logger.info("✅ Successfully initialized tiktoken with o200k_base")
                return encoding
                
            except Exception as e2:
                logger.warning(f"Failed to load o200k_base encoding: {e2}")
                
                try:
                    logger.info("Attempting tiktoken with p50k_base encoding")
                    encoding = tiktoken.get_encoding("p50k_base")
                    logger.info("✅ Successfully initialized tiktoken with p50k_base")
                    return encoding
                    
                except Exception as e3:
                    logger.error(f"All tiktoken encodings failed. Using character-based estimation.")
                    return None
    
    def _get_safe_filing_type_value(self, filing_type: Union[FilingType, str]) -> str:
        """Safely get filing type value"""
        if isinstance(filing_type, str):
            return filing_type
        elif hasattr(filing_type, 'value'):
            return filing_type.value
        elif isinstance(filing_type, FilingType):
            return filing_type.value
        else:
            logger.warning(f"Unexpected filing_type type: {type(filing_type)}")
            return str(filing_type)
    
    def _get_safe_ticker(self, filing: Filing) -> str:
        """Get ticker safely"""
        if filing.ticker:
            return filing.ticker
        elif filing.company and filing.company.ticker:
            return filing.company.ticker
        else:
            if filing.filing_type == FilingType.FORM_S1:
                if filing.company and filing.company.name:
                    name_parts = filing.company.name.split()
                    return name_parts[0][:10] if name_parts else "PRE-IPO"
                elif filing.company and filing.company.cik:
                    return f"CIK{filing.company.cik}"
            return "UNKNOWN"
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens with fallback"""
        if self.encoding is None:
            return len(text) // 4
        
        try:
            return len(self.encoding.encode(text))
        except Exception as e:
            logger.warning(f"Token counting failed: {e}. Using character-based estimation.")
            return len(text) // 4
    
    def _validate_data_marking(self, text: str) -> Tuple[bool, List[str]]:
        """Validate data source markings"""
        issues = []
        
        numbers = re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', text)
        
        unmarked_numbers = 0
        for number in numbers[:15]:
            pos = text.find(number)
            if pos == -1:
                continue
                
            nearby_text = text[max(0, pos-100):pos+100]
            has_citation = any(
                re.search(pattern, nearby_text) 
                for pattern in DATA_SOURCE_PATTERNS.values()
            )
            
            if not has_citation:
                unmarked_numbers += 1
                if unmarked_numbers <= 3:
                    issues.append(f"Unmarked number: {number}")
        
        total_markings = sum(
            len(re.findall(pattern, text)) 
            for pattern in DATA_SOURCE_PATTERNS.values()
        )
        
        text_length = len(text)
        if text_length > 1000:
            expected_markings = max(5, text_length // 500)
            if total_markings < expected_markings:
                issues.append(f"Insufficient data source markings: {total_markings}/{expected_markings} expected")
        
        suspicious_patterns = [
            r'\$X\.XB', r'\$\d+\.XB', r'TBD', r'INSERT.*HERE', 
            r'PLACEHOLDER', r'\[AMOUNT\]', r'\[NUMBER\]'
        ]
        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(f"Suspicious placeholder content detected: {pattern}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def _smart_truncate_content(self, content: str, max_tokens: int, filing_type: Union[FilingType, str]) -> str:
        """Intelligently truncate content"""
        current_tokens = self._count_tokens(content)
        
        if current_tokens <= max_tokens:
            return content
        
        logger.info(f"Content needs truncation: {current_tokens} tokens > {max_tokens} limit")
        
        sections = content.split('\n\n')
        filing_type_value = self._get_safe_filing_type_value(filing_type)
        
        priority_keywords = {
            'FORM_10K': ['management discussion', 'financial statements', 'risk factors', 'business'],
            'FORM_10Q': ['financial statements', 'management discussion', 'quarter', 'three months'],
            'FORM_8K': ['item', 'event', 'agreement', 'announcement', 'exhibit 99'],
            'FORM_S1': ['summary', 'risk factors', 'use of proceeds', 'business']
        }
        
        scored_sections = []
        filing_keywords = priority_keywords.get(filing_type_value, [])
        
        for section in sections:
            score = 0
            section_lower = section.lower()
            
            for keyword in filing_keywords:
                if keyword in section_lower:
                    score += 10
            
            if '|' in section and '---' in section:
                score += 20
            
            score += len(re.findall(r'\$[\d,]+', section)) * 2
            score += len(re.findall(r'\d+\.?\d*%', section)) * 2
            
            if any(term in section_lower for term in ['management', 'executive', 'ceo', 'cfo']):
                score += 15
            
            scored_sections.append((score, section))
        
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        
        truncated_parts = []
        total_tokens = 0
        
        for score, section in scored_sections:
            section_tokens = self._count_tokens(section)
            if total_tokens + section_tokens <= max_tokens:
                truncated_parts.append(section)
                total_tokens += section_tokens
            elif total_tokens < max_tokens * 0.9:
                remaining_tokens = max_tokens - total_tokens
                partial_section = section[:remaining_tokens * 4]
                truncated_parts.append(partial_section + "\n[Section truncated...]")
                break
        
        result = '\n\n'.join(truncated_parts)
        logger.info(f"Truncated content from {current_tokens} to {self._count_tokens(result)} tokens")
        
        return result
        
    async def process_filing(self, db: Session, filing: Filing) -> bool:
        """Process a filing using unified AI analysis"""
        try:
            filing.status = ProcessingStatus.ANALYZING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            ticker = self._get_safe_ticker(filing)
            company_name = filing.company.name if filing.company else "Unknown Company"
            filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
            
            logger.info(f"Starting v10 Flash Note AI processing (o3-mini) for {ticker} {filing_type_value}")
            
            # Fetch FMP company profile
            await self._fetch_and_store_fmp_data(db, filing, ticker)
            
            # ✅ Fetch analyst estimates for 10-Q/10-K
            await self._fetch_and_store_analyst_estimates(db, filing, ticker)
            
            # Get filing directory
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            
            # Extract text
            sections = text_extractor.extract_from_filing(filing_dir)
            
            if 'error' in sections:
                raise Exception(f"Text extraction failed: {sections['error']}")
            
            primary_content = sections.get('enhanced_text', '') or sections.get('primary_content', '')
            full_text = sections.get('full_text', '')
            
            if sections.get('enhanced_text'):
                logger.info(f"Using enhanced Markdown content: {len(primary_content)} chars")
            
            # 8-K Exhibit integration
            if filing.filing_type == FilingType.FORM_8K:
                exhibit_content = sections.get('important_exhibits_content', '') or sections.get('exhibit_99_content', '')
                if exhibit_content and len(exhibit_content) > 100:
                    logger.info(f"Integrating exhibit content: {len(exhibit_content)} chars")
                    primary_content += f"\n\n{'='*60}\nEXHIBIT CONTENT (PRESS RELEASE/FINANCIAL DATA)\n{'='*60}\n\n{exhibit_content}"
            
            if not primary_content or len(primary_content) < 100:
                raise Exception("Insufficient text content extracted")
            
            logger.info(f"Extracted content - Primary: {len(primary_content)} chars")
            
            # Generate unified analysis with retry
            unified_result = await self._generate_unified_analysis_with_retry(
                filing, primary_content, full_text
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.references = unified_result.get('references', [])
            filing.analysis_version = "v11_o3mini"
            
            # Extract supplementary fields
            await self._extract_supplementary_fields(filing, unified_result, primary_content, full_text)
            
            # Set status
            filing.status = ProcessingStatus.COMPLETED
            filing.processing_completed_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"✅ v10 Flash Note AI processing (o3-mini) completed for {filing.accession_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error in v10 AI processing: {e}")
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            return False
    
    async def _fetch_and_store_fmp_data(self, db: Session, filing: Filing, ticker: str):
        """Fetch FMP company profile for enrichment"""
        if not ticker or ticker in ["UNKNOWN", "PRE-IPO"] or ticker.startswith("CIK"):
            return
        
        company = filing.company
        if not company:
            return
        
        needs_fmp_data = (
            not company.market_cap or 
            not company.analyst_consensus or 
            not company.website
        )
        
        if not needs_fmp_data:
            logger.info(f"[FMP Integration] Company {ticker} already has FMP data")
            return
        
        try:
            logger.info(f"[FMP Integration] Fetching company profile from FMP for {ticker}")
            fmp_data = fmp_service.get_company_profile(ticker)
            
            if fmp_data:
                company_updates = {}
                
                if fmp_data.get('market_cap'):
                    company_updates['market_cap'] = fmp_data['market_cap'] / 1e6
                
                if fmp_data.get('website'):
                    company_updates['website'] = fmp_data['website']
                
                # 获取分析师共识评级
                analyst_consensus = fmp_service.get_analyst_consensus(ticker)
                if analyst_consensus:
                    company_updates['analyst_consensus'] = analyst_consensus
                
                for field, value in company_updates.items():
                    setattr(company, field, value)
                
                if fmp_data.get('sector') and not company.sector:
                    company.sector = fmp_data['sector']
                
                if fmp_data.get('industry') and not company.industry:
                    company.industry = fmp_data['industry']
                
                company.updated_at = datetime.utcnow()
                logger.info(f"[FMP Integration] Successfully updated company {ticker}")
                
        except Exception as e:
            logger.error(f"[FMP Integration] Error fetching FMP data for {ticker}: {e}")
    
    async def _fetch_and_store_analyst_estimates(self, db: Session, filing: Filing, ticker: str):
        """
        ✅ Fetch analyst estimates and store in filing
        Only for 10-Q and 10-K filings
        """
        # Only for quarterly and annual reports
        if filing.filing_type not in [FilingType.FORM_10Q, FilingType.FORM_10K]:
            return
        
        if not ticker or ticker in ["UNKNOWN", "PRE-IPO"] or ticker.startswith("CIK"):
            logger.info(f"[FMP Estimates] Skipping for invalid ticker: {ticker}")
            return
        
        try:
            logger.info(f"[FMP Estimates] Fetching latest estimates for {ticker}")
            
            # Use optimized method to get latest estimates
            estimates = fmp_service.get_latest_analyst_estimates(ticker)
            
            if estimates:
                # Store in filing record
                filing.estimate_eps = estimates.get('eps')
                filing.estimate_revenue = estimates.get('revenue')
                
                db.commit()
                
                logger.info(
                    f"[FMP Estimates] Stored for {ticker}: "
                    f"EPS=${estimates.get('eps')}, Revenue=${estimates.get('revenue')}B"
                )
            else:
                logger.info(f"[FMP Estimates] No estimates available for {ticker}")
                
        except Exception as e:
            logger.error(f"[FMP Estimates] Error for {ticker}: {e}")
            # Don't fail filing processing if FMP fails
    
    async def _generate_unified_analysis_with_retry(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str
    ) -> Dict:
        """Generate unified analysis with intelligent retry"""
        max_retries = 3
        
        for attempt in range(max_retries):
            logger.info(f"Analysis attempt {attempt + 1}/{max_retries}")
            
            processed_content = self._preprocess_content_for_ai(
                primary_content, full_text, filing.filing_type, attempt
            )
            
            unified_result = await self._generate_unified_analysis(
                filing, processed_content, processed_content
            )
            
            is_valid, validation_issues = self._validate_data_marking(unified_result['unified_analysis'])
            
            if not is_valid:
                logger.warning(f"Data marking validation failed (attempt {attempt + 1}): {validation_issues}")
                if attempt < max_retries - 1:
                    continue
            
            word_count = len(unified_result['unified_analysis'].split())
            
            if filing.filing_type == FilingType.FORM_10K:
                target_min = 600
            elif filing.filing_type == FilingType.FORM_10Q:
                target_min = 600
            elif filing.filing_type == FilingType.FORM_8K:
                target_min = 400
            elif filing.filing_type == FilingType.FORM_S1:
                target_min = 600
            else:
                target_min = 500
            
            if self._contains_template_numbers(unified_result['unified_analysis']):
                logger.warning(f"Template numbers detected, retrying... (attempt {attempt + 1})")
                continue
            
            if not self._validate_content_quality(unified_result['unified_analysis'], filing.filing_type):
                logger.warning(f"Content quality check failed, retrying... (attempt {attempt + 1})")
                continue
            
            if word_count >= target_min:
                logger.info(f"Generated {word_count} words, within acceptable range")
                break
            elif attempt < max_retries - 1:
                logger.warning(f"Word count {word_count} below target {target_min}, enhancing...")
                continue
        
        unified_result['unified_analysis'] = self._optimize_markup_density(
            unified_result['unified_analysis']
        )
        
        return unified_result
    
    def _preprocess_content_for_ai(self, primary_content: str, full_text: str, filing_type: Union[FilingType, str], attempt: int) -> str:
        """Preprocess content for AI"""
        if attempt == 0:
            content = primary_content
        else:
            content = primary_content + "\n\n[Additional Context]\n\n" + full_text[len(primary_content):len(primary_content) + 20000 * attempt]
        
        prompt_tokens = 2000
        available_tokens = self.max_input_tokens - prompt_tokens - self.target_output_tokens
        
        content = self._smart_truncate_content(content, available_tokens, filing_type)
        content = self._clean_content_for_ai(content)
        
        logger.info(f"Preprocessed content: {self._count_tokens(content)} tokens")
        
        return content
    
    def _clean_content_for_ai(self, content: str) -> str:
        """Clean content for AI processing"""
        legal_patterns = [
            r'PURSUANT TO THE REQUIREMENTS.*?(?=\n\n|\Z)',
            r'The information.*?incorporated by reference.*?(?=\n\n|\Z)',
            r'SIGNATURES?\s*\n.*?\Z',
        ]
        
        for pattern in legal_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
        
        content = re.sub(r'\n{4,}', '\n\n\n', content)
        content = re.sub(r' {3,}', ' ', content)
        content = re.sub(r'Page \d+ of \d+', '', content)
        
        return content.strip()
    
    def _validate_content_quality(self, analysis: str, filing_type: Union[FilingType, str]) -> bool:
        """Validate analysis quality"""
        if isinstance(filing_type, str):
            filing_type_value = filing_type
        else:
            filing_type_value = self._get_safe_filing_type_value(filing_type)
        
        financial_mentions = len(re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', analysis))
        
        if filing_type_value in ['FORM_10K', '10-K', 'FORM_10Q', '10-Q']:
            if financial_mentions < 5:
                logger.warning(f"Insufficient financial data: {financial_mentions} mentions")
                return False
        
        paragraphs = [p for p in analysis.split('\n\n') if len(p) > 100]
        if len(paragraphs) < 3:
            logger.warning("Insufficient substantive paragraphs")
            return False
        
        total_markings = sum(
            len(re.findall(pattern, analysis)) 
            for pattern in DATA_SOURCE_PATTERNS.values()
        )
        if total_markings < 3:
            logger.warning(f"Insufficient data source markings: {total_markings}")
            return False
        
        return True
    
    def _contains_template_numbers(self, text: str) -> bool:
        """Check for template numbers"""
        template_patterns = [
            r'\$5\.2B', r'exceeded.*by.*6%', r'\$4\.9B',
            r'placeholder', r'INSERT.*HERE', r'TBD',
            r'\$X\.X+B', r'\d+\.X+%',
        ]
        
        for pattern in template_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    async def _generate_unified_analysis(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str
    ) -> Dict:
        """Generate unified analysis with filing-specific prompts"""
        content = primary_content
        
        filing_context = self._build_filing_context(filing)
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        # ✅ UPDATED: Use new Flash Note prompt for 10-Q
        if filing_type_value in ['FORM_10Q', '10-Q']:
            prompt = self._build_10q_unified_prompt_enhanced(filing, content, filing_context)
        elif filing_type_value in ['FORM_10K', '10-K']:
            prompt = self._build_10k_unified_prompt_enhanced(filing, content, filing_context)
        elif filing_type_value in ['FORM_8K', '8-K']:
            prompt = self._build_8k_unified_prompt(filing, content, filing_context)
        elif filing_type_value in ['FORM_S1', 'S-1']:
            prompt = self._build_s1_unified_prompt_enhanced(filing, content, filing_context)
        else:
            prompt = self._build_generic_unified_prompt(filing, content, filing_context)
        
        prompt_tokens = self._count_tokens(prompt)
        logger.info(f"Prompt tokens: {prompt_tokens}")
        
        unified_analysis, references = await self._generate_text_with_search(
            prompt, 
            max_tokens=settings.AI_UNIFIED_ANALYSIS_MAX_TOKENS
        )
        
        feed_summary = await self._generate_feed_summary_from_unified(
            unified_analysis, 
            filing_type_value,
            filing
        )
        
        markup_data = self._extract_markup_data(unified_analysis)
        
        return {
            'unified_analysis': unified_analysis,
            'feed_summary': feed_summary,
            'markup_data': markup_data,
            'references': references
        }
    
    def _build_filing_context(self, filing: Filing) -> Dict:
        """
        ✅ UPDATED: Build context with FMP estimates
        """
        context = {
            'company_name': filing.company.name if filing.company else "the company",
            'ticker': self._get_safe_ticker(filing),
            'fiscal_year': filing.fiscal_year,
            'fiscal_quarter': filing.fiscal_quarter,
            'period_end_date': filing.period_end_date.strftime('%B %d, %Y') if filing.period_end_date else None,
            'filing_date': filing.filing_date.strftime('%B %d, %Y'),
            'current_date': datetime.now().strftime('%B %d, %Y'),
        }
        
        # ✅ NEW: Add FMP estimates if available
        if hasattr(filing, 'estimate_eps') and filing.estimate_eps:
            context['estimate_eps'] = filing.estimate_eps
        
        if hasattr(filing, 'estimate_revenue') and filing.estimate_revenue:
            context['estimate_revenue'] = filing.estimate_revenue
        
        if filing.filing_type == FilingType.FORM_8K:
            context['event_type'] = self._identify_8k_event_type(filing.primary_content if hasattr(filing, 'primary_content') else '')
            context['item_type'] = filing.item_type if hasattr(filing, 'item_type') else ''
            
        return context
    
    def _build_data_marking_instructions(self) -> str:
        """Data source attribution instructions"""
        return """
CRITICAL: Data Source Attribution System
=========================================
Every factual claim MUST be attributed to its source:

1. [DOC: location] - From THIS filing
   Examples: [DOC: Income Statement], [DOC: MD&A]

2. [1], [2], [3]... - Web search results
   Use for external data: industry trends, competitor metrics, analyst perspectives

3. [FMP] - FMP analyst consensus data
   Use ONLY for pre-provided estimate numbers

4. [CALC: formula] - Your calculations
   Example: [CALC: $XX.XB/$XX.XB - 1 = X.X% YoY]

5. [NO_DATA] - Information unavailable

6. [CAUTION] - Inferences with uncertainty

RULES:
- Financial figures without citations = REJECTED
- Never invent consensus figures
- Search when external context adds material insight
"""
    
    def _build_10q_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """
        ✅ Enhanced 10-Q prompt v2.0: Quarterly Performance Snapshot
        Key improvements: Insight-driven headers + Guidance handling + Placeholder examples
        """
        marking_instructions = self._build_data_marking_instructions()
        
        # Build beat/miss context if estimates available
        beat_miss_section = ""
        critical_estimates = ""
        if context.get('estimate_eps') or context.get('estimate_revenue'):
            beat_miss_section = self._build_beat_miss_context(context)
            # Build critical estimates reminder
            critical_estimates = "CRITICAL - ANALYST CONSENSUS (FMP):\n"
            if context.get('estimate_revenue'):
                critical_estimates += f"- Revenue Estimate: ${context['estimate_revenue']}B\n"
            if context.get('estimate_eps'):
                critical_estimates += f"- EPS Estimate: ${context['estimate_eps']}\n"
            critical_estimates += "\n"
        
        return f"""You are a sell-side equity analyst at a top-tier investment bank writing a flash note to institutional clients immediately after {context['company_name']}'s 10-Q filing.

Your clients are Portfolio Managers at hedge funds and mutual funds. They receive 100+ research emails per day.

**10-Q Purpose: Quarterly Performance Snapshot**

Focus on THIS quarter:
- How did this quarter perform vs. expectations?
- What drove the beat/miss?
- What are the near-term catalysts or risks?
- What's the outlook for next quarter?

Keep it focused on the quarterly story, not long-term strategy (save that for 10-K).

{critical_estimates}{marking_instructions}

## OUTPUT STRUCTURE (MANDATORY)

---

### SECTION 1: FACT CLARITY

**Format Requirements**:

**Bullet Points** (8-12 bullets):
- Each bullet = One metric only
- Format: `• **Metric Name**: $X.XB, +X% YoY [Source] - Commentary`
- Use abbreviations: YoY, QoQ, v/s
- Bold **BEAT** or **MISS** vs. consensus when applicable [FMP]
- Most important metrics first (Revenue, EPS always top 2)

**MANDATORY FIRST TWO BULLETS** (if estimates available):
• **Total Revenue**: $X.XB, +X% YoY [DOC: Income Statement] - **BEAT/MISS** by $X.XB vs. estimate [FMP]
• **Diluted EPS**: $X.XX, +X% YoY [DOC] - **BEAT/MISS** by $X.XX vs. consensus [FMP]

**Length**: 300-450 words maximum

Goal: Traders can scan key numbers in 10 seconds.

**BEFORE WRITING SECTION 1 - DO THIS CALCULATION FIRST**:
If analyst estimates are available [FMP]:
  Step 1: Find Actual Revenue in [DOC: Income Statement]
  Step 2: Find Actual EPS (Diluted) in [DOC: Income Statement]
  Step 3: Calculate Beat/Miss:
    - Revenue Delta = Actual Revenue - Estimate Revenue
    - EPS Delta = Actual EPS - Estimate EPS
    - If Delta > 0: Write "**BEAT** by $X.XX"
    - If Delta < 0: Write "**MISS** by $X.XX"
    - If Delta = 0: Write "**IN-LINE**"
  
  CRITICAL: Do NOT reverse the direction. Actual > Estimate = BEAT.
  
Then write your bullets using these calculated results.

---

### SECTION 2: MARKET PERSPECTIVE

**Purpose**: Provide context and conviction for position sizing

**Format Requirements**:

1. **Structure with THESIS-DRIVEN Headers**:
   
   Each major paragraph needs a header that states your KEY FINDING (3-7 words).
   
   Headers should answer: "What did I discover?" not "What am I analyzing?"
   The paragraph then provides evidence supporting the header.
   
   **Write 3-4 thesis-driven paragraphs with headers:**
   
   Format: `## Header Text` (no emoji, just clear insight statement)
   
   Examples:
   - `## Strong Revenue Growth Drives Performance`
   - `## Raw Material Costs Pressure Margins`
   - `## Industry Tailwinds Support Demand`
   
   **Headers should be INSIGHT-driven, not administrative:**
   ✅ Good: "Industry Tailwinds Support Demand"
   ✅ Good: "Raw Material Costs Pressure Margins"  
   ❌ Bad: "Forward Outlook Lacks Specific Guidance"
   ❌ Bad: "Management Commentary on Future"

2. **Forward Outlook Structure**:
   
   Write a "Forward Outlook" paragraph covering:
   - Industry trends and market context (use [web_search] for peer data if material)
   - Key catalysts (positive drivers for next quarter/year)
   - Key risks (headwinds or challenges)
   - Management guidance (ONLY if explicitly provided with numeric targets)
   
   **Guidance Handling**:
   - IF management provides explicit numeric guidance (revenue/EPS ranges or targets):
     * State it clearly: "Management guided Q4 revenue to $X.XB-$X.XB [DOC: MD&A]"
     * Include rationale if given
   - IF no explicit guidance is provided:
     * DO NOT mention the absence of guidance
     * Focus on industry trends, peer comparisons, and business drivers instead
   
   **Priority Order** (lead with what matters most):
   1. Industry trends and competitive context
   2. Material catalysts or risks
   3. Guidance (only if provided)
   
   Do NOT compare to prior guidance or calculate changes.

3. **Length**: 600-800 words (strict max: 900 words)

4. **Broader Context**:

Quarterly results reflect both company execution and the environment in which the company operates. 

Use web search to understand whether this quarter's performance is remarkable given the circumstances, or simply riding industry momentum. Is revenue growth impressive because it outpaced a weak market, or merely kept pace with a rising tide? Are margin pressures company-specific missteps, or unavoidable cost inflation hitting the entire sector?

Search for the context the filing can't provide: what's happening in the world outside this company's four walls.

Integrate what you find into your narrative. External context should illuminate, not just decorate.

Goal: Provide conviction for position sizing decisions.

---

## CRITICAL RULES

**Style**:
- Active voice: "Revenue grew X%" not "was up X%"
- Specific: "$X.XB" not "approximately X billion"
- Lead with numbers: "EPS $X.XX beat by $X.XX"
- No vague terms without data: avoid "significant", "impressive" alone

**DON'T**:
- Repeat info between sections
- Speculate without data
- Use marketing language: "game-changing", "revolutionary"

---

{beat_miss_section}

## COMPANY CONTEXT

- **Company**: {context['company_name']} ({context['ticker']})
- **Quarter**: {context.get('fiscal_quarter', 'Q3')} {context.get('fiscal_year', '2025')}
- **Period End**: {context.get('period_end_date', 'N/A')}
- **Filing Date**: {context['filing_date']}

---

## FILING CONTENT

{content}

---

Now generate your two-section analysis following this structure.

**SECTION 1: FACT CLARITY** - 8-12 bullets (max 450 words)
**SECTION 2: MARKET PERSPECTIVE** - Analyst commentary (600-800 words)

---

## VISUAL ENHANCEMENT (Professional Readability)

Apply these lightweight visual markings to improve scannability:

**Three types of inline emphasis:**

1. **Yellow Highlight** (**...**):
   - Numbers and metrics: **$X.XB**, **X%**, **$X.XX**
   - Beat/Miss indicators: **BEAT**, **MISS**, **IN-LINE**
   - YoY/QoQ changes: **+X%**, **-X%**

2. __Bold Text__ (__...__):
   - Key business concepts: __digital transformation__, __robust demand__
   - Important conclusions: __exceeded expectations__, __strong execution__
   - Strategic terms: __competitive advantage__, __market leadership__

3. *Italic Text* (*...*):
   - Cautionary language: *monitor closely*, *potential pressure*
   - Risk indicators: *headwind*, *challenge*, *uncertainty*
   - Tentative statements: *if conditions persist*, *subject to change*

**Structural markup:**

- Use `---` horizontal separators between major discussion points
- Use `## Subheader` for thesis-driven paragraph headers (no emoji)
- Example:
  ```
  ## Strong Revenue Growth Drives Performance
  
  Revenue reached **$14.883B**, driven by __robust demand__ in 
  the Networking segment. However, *monitor closely* the margin pressure...
  
  ---
  
  ## Margin Pressures Require Attention
  ```

**Application guidelines:**

- Section 1 (FACT CLARITY): Yellow highlights on numbers only
- Section 2 (MARKET PERSPECTIVE): All three types as appropriate
- Use sparingly - emphasis loses impact if overused
- Most text should remain plain for professional appearance
"""
    
    def _build_beat_miss_context(self, context: Dict) -> str:
        """
        ✅ Build structured beat/miss reference table
        """
        eps_estimate = context.get('estimate_eps')
        revenue_estimate = context.get('estimate_revenue')
        
        if not eps_estimate and not revenue_estimate:
            return ""
        
        table_rows = []
        
        if eps_estimate:
            table_rows.append(f"| EPS (Diluted) | ${eps_estimate:.2f} | [FMP] |")
        
        if revenue_estimate:
            table_rows.append(f"| Revenue | ${revenue_estimate:.1f}B | [FMP] |")
        
        table = "\n".join(table_rows)
        
        return f"""
## CRITICAL: Beat/Miss Reference Data

**IMPORTANT**: This section contains PRE-VERIFIED analyst consensus from FMP.

### Analyst Consensus Estimates

| Metric | Consensus Estimate | Source |
|--------|-------------------|---------|
{table}

### YOUR ANALYSIS WORKFLOW:

**Step 1 - Extract Actuals from Filing**:
Look for "Diluted earnings per share" and "Total revenue" in financial statements.

Write in FACT CLARITY section:
- **Diluted EPS**: $X.XX [DOC: Income Statement]
- **Revenue**: $XX.XB [DOC: Income Statement]

**Step 2 - Determine Beat/Miss**:
FOR EPS:
- If Actual EPS > Estimate: Write "BEAT by $X.XX"
- If Actual EPS < Estimate: Write "MISS by $X.XX"
- If Actual EPS = Estimate: Write "IN-LINE"

FOR REVENUE: Same logic

**Step 3 - Explain in MARKET PERSPECTIVE**:
Why did the company beat/miss? What does this tell us about execution and market conditions?

Do NOT recalculate. Use the comparison from Step 2 directly.

---
"""
    
    def _build_10k_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """
        10-K prompt - Annual strategic review for retail investors v2.0
        核心定位：帮助投资者理解公司年度表现、战略方向和关键风险
        关键改进：观点型标题 + 故事化叙事 + 投资者视角 + 风险聚焦
        """
        marking_instructions = self._build_data_marking_instructions()
        
        ticker = self._get_safe_ticker(filing)
        company_name = context['company_name']
        
        return f"""You are a financial analyst writing an annual report analysis for retail investors.

⚠️ DATA INTEGRITY: All numbers must cite sources [DOC: section] or [NO_DATA]. Never estimate or fabricate.

Your goal: Help investors understand what happened this year and what it means for the company's future.

Think of this as an "Annual Strategic Review" - not just numbers, but the story behind them and where the company is headed.

{marking_instructions}

## CORE PRINCIPLE: Story + Strategy + Investment Implications

Your readers want to know:
1. **What happened this year?** (Performance story with context)
2. **Where is the company going?** (Strategic direction)
3. **What are the key risks?** (Deal-breakers, not checklists)
4. **What should I do with this information?** (Investment perspective)

Annual reports are about understanding the BIG PICTURE, not quarter-to-quarter details.

---

## OUTPUT STRUCTURE (MANDATORY)

**CRITICAL**: Your analysis MUST follow this exact three-section structure with proper section headers:

```
### SECTION 1: ANNUAL REVIEW
[Content with 2-3 thesis-driven paragraphs]

### SECTION 2: STRATEGIC DIRECTION  
[Content with 2-3 thesis-driven paragraphs including risks]

### SECTION 3: INVESTMENT PERSPECTIVE
[Final synthesis and investor guidance]
```

Each section MUST start with the "### SECTION X:" header (exactly as shown).
Within each section, use thesis-driven subheaders: `## Header Text`

---

### SECTION 1: ANNUAL REVIEW
**Reading Time**: 2-3 minutes

**Structure: 3-4 paragraphs with THESIS-DRIVEN headers**

---

## [Your Performance Conclusion Header]

Write a header that captures the KEY PERFORMANCE STORY (5-9 words)

The header should state your key finding, not just label the topic.
Think: "What's the story?" not "What section is this?"

**Content**:
Tell the performance story with 3-year context:
- Revenue trend (3-year trajectory, not just YoY)
- What drove the change? (Customer wins/losses, market dynamics, product mix)
- Profitability trend (margins, operating income, net income)
- Key expense changes if material (R&D ramp, restructuring)

Use specific numbers but focus on the NARRATIVE:
- Don't just list: "Revenue was $X in 2025, $Y in 2024, $Z in 2023"
- Instead tell: "Revenue declined for the second year, falling to $X from a $Z peak in 2023, driven by..."

Cite [DOC: Consolidated Statements of Operations; MD&A]

---

## [Your Balance Sheet/Cash Flow Conclusion Header]

Write a header that captures FINANCIAL POSITION or CAPITAL ALLOCATION story (5-9 words)

The header should state your key finding about the company's financial health or capital use.

**Content**:
Focus on what matters for investors:
- Cash position and trend (and why it changed)
- Operating cash flow strength
- Capital deployment (buybacks, dividends, capex, M&A)
- Debt levels and any near-term maturities
- Working capital if material

Skip: Detailed line-item changes unless they tell a story

Cite [DOC: Consolidated Balance Sheets; Statements of Cash Flows]

---

### SECTION 2: STRATEGIC DIRECTION
**Reading Time**: 4-5 minutes

**Structure: 3-4 sections with THESIS-DRIVEN headers**

---

## [Your Strategy Conclusion Header]

Write a header that captures STRATEGIC DIRECTION or KEY INITIATIVE (5-9 words)

The header should state what the company is doing or betting on, not just "strategy."

**Content**:
Explain the company's strategic direction:
- What are they focused on? (Markets, products, capabilities)
- Any major initiatives? (M&A, partnerships, capex programs, restructuring)
- What's the rationale? (Why this strategy makes sense)

**Strategic Context Through Search**:

Annual reports describe what management is doing, but rarely explain why now, or how this compares to what's happening across the industry.

Use web search to understand the forces shaping strategic decisions. If the company is making a major acquisition, what's driving M&A activity in this sector? If they're pivoting to a new business model, are peers doing the same? If they're investing heavily in a technology, what's the competitive landscape?

The filing tells you the strategy. Search tells you whether it's visionary or reactive, early or late, bold or necessary.

If there's a MAJOR strategic event (merger, spin-off, major acquisition), lead with that and search for context that explains its significance.

Cite [DOC: MD&A; Item 1 - Business] for the strategy itself, and [1], [2] for external context.

---

## [Your Risk Conclusion Header]

Write a header that captures the TOP 2-3 RISKS (5-9 words)

The header should name the specific risks, not just say "risks."

**Content**:
Identify and explain 2-3 DEAL-BREAKER risks:

What's a deal-breaker risk in a 10-K context?
- Could materially alter the investment thesis
- Examples: Major customer concentration, regulatory existential threat, debt covenant risk, competitive disruption, M&A integration failure

Format as numbered sub-risks:
**1. [Risk Name]**: [2-3 sentences: what it is + why it matters + cite source]
**2. [Risk Name]**: [2-3 sentences: what it is + why it matters + cite source]
**3. [Risk Name]**: [2-3 sentences: what it is + why it matters + cite source]

Then add: "Additional considerations include [brief mention of 2-3 secondary risks in ONE sentence]."

What to SKIP:
- Generic risks every company has (competition, macro, general market conditions)
- Boilerplate language from Risk Factors section
- Minor operational or compliance risks unless material

Cite [DOC: Risk Factors]

---

## [Outlook/Future Direction Header - OPTIONAL]

Include only if management provides specific guidance or forward-looking commentary

Examples:
- "FY2026 Guidance: Targeting Revenue Growth Return"
- "Management Signals Cautious Near-Term Outlook"

**Content** (if included):
- Management's stated priorities or guidance
- Key milestones or catalysts to monitor
- Cite [DOC: MD&A]

---

### SECTION 3: INVESTMENT PERSPECTIVE

**Content** (MANDATORY):

Synthesize everything into actionable perspective for investors.

Address the fundamental question: What kind of investment is this, and what do investors need to believe for it to work?

Your analysis should help investors understand:
- What phase is this company in? (turnaround, growth, maturity, distress)
- What's the core investment debate or uncertainty?
- What needs to happen for this to succeed?
- What are the key watch items in coming quarters?

Write naturally. Don't force structure. Let the company's situation dictate what matters most.

**Length**: 200-300 words

---

## FORMATTING RULES (Readability First)

**Header Format**:
- Use: `## Header Text` for subheaders
- Keep headers SHORT: 5-9 words
- Headers = CONCLUSIONS (what you found), not labels (what section this is)
- Include numbers or concrete terms when impactful

**Visual Marking** (use the three inline emphasis types):
- **Yellow highlight** for numbers: **$4.09B**, **12.2%**
- __Bold text__ for key concepts: __strategic shift__, __competitive advantage__
- *Italic text* for cautionary terms: *subject to approval*, *potential risk*

**Narrative Flow**:
- Write in paragraphs, not bullet lists (except for numbered risks)
- Tell a story, don't just report data
- Connect the dots: "Revenue fell BECAUSE... which LED TO... RESULTING IN..."

---

## CRITICAL RULES

**Length Discipline** (ABSOLUTE):
- Section 1: 280-350 words MAX
- Section 2: 500-650 words MAX  
- Total: 780-1000 words
- If approaching limit: Cut weaker points, don't compress language

**Content Focus: Big Picture, Not Details**

10-K is about the ANNUAL STORY and STRATEGIC DIRECTION, not quarter-by-quarter minutiae.

Include what matters:
- Multi-year trends (3-year context preferred)
- Major strategic initiatives or changes
- 2-3 deal-breaker risks (not risk catalog)
- Investment implications (who should care and why)

Ruthlessly cut:
- Quarterly fluctuation details (save for 10-Q)
- Granular line-item changes without strategic significance
- Generic industry background
- Long lists of minor risks
- Boilerplate language from the filing

Avoid hype language and speculation beyond stated plans.

**Style**:
- Narrative prose, not data dump
- Active voice, specific numbers, plain language
- Write like a strategy consultant presenting annual review, not an accountant reading financials

---

## COMPANY CONTEXT

- **Company**: {company_name} ({ticker})
- **Fiscal Year Ended**: {context['filing_date']}
- **Filing Type**: Annual Report (10-K)

---

## FILING CONTENT

{content}

---

Now generate your two-section analysis:

**SECTION 1: ANNUAL REVIEW** - Performance story + financial position with THESIS-DRIVEN headers (280-350 words)
**SECTION 2: STRATEGIC DIRECTION** - Strategy + risks + investment perspective with THESIS-DRIVEN headers (500-650 words)

Remember:
- This is an ANNUAL STRATEGIC REVIEW, not a quarterly earnings recap
- Headers should be YOUR CONCLUSIONS, not generic labels
- Focus on multi-year trends and strategic direction
- Include "Investment Perspective" to help readers understand implications
- Be ruthless about cutting non-essential details
"""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """
        8-K prompt using Financial News Analyst style
        Structure: EVENT SNAPSHOT + IMPACT ANALYSIS
        ENHANCED: Inject official SEC Item guidance when available
        """
        marking_instructions = self._build_data_marking_instructions()
        
        # Get official Items from filing (populated by edgar_scanner)
        official_items = filing.event_items if filing.event_items else None
        
        # Get official guidance
        if official_items:
            guidance = self._get_official_item_guidance(official_items)
            logger.info(f"Using official Item guidance: {guidance['item_number']} - {guidance['title']}")
        else:
            # Try to extract from content as fallback
            content_lower = content.lower()
            item_pattern = r'item\s+(\d+\.\d+)'
            items_in_content = re.findall(item_pattern, content_lower)
            if items_in_content:
                official_items = items_in_content
                guidance = self._get_official_item_guidance(items_in_content)
                logger.info(f"Extracted Items from content: {items_in_content}")
            else:
                guidance = self._get_official_item_guidance(None)
        
        # Special handling for Item 2.02 (Earnings Release)
        if guidance['category'] == 'Earnings Release':
            logger.info("Detected Item 2.02 earnings 8-K, using 10-Q prompt structure")
            return self._build_10q_unified_prompt_enhanced(filing, content, context)
        
        # Build official guidance section
        item_guidance = f"""
## SEC OFFICIAL CLASSIFICATION

The SEC has classified this 8-K filing as:

**Item {guidance['item_number'] or 'N/A'}**: {guidance['title']}

**Category**: {guidance['category']}

**What this means**: {guidance['description']}

---

## ANALYSIS APPROACH

**Content-Driven Analysis**:

Let the filing content guide your analysis. Based on the event category above, identify and explain what matters most to investors from what's actually disclosed in the document.

Focus on substance over checklist completion. Your goal is to provide insight, not to mechanically fill fields. If certain details aren't material or aren't disclosed, don't force them into the analysis.

Ask yourself:
- What is the nature and significance of this event?
- What are the key terms or facts that impact the company's position?
- Why is this happening now?
- What should investors pay attention to?

---
"""
        
        # Standard 8-K prompt with official guidance
        return f"""You are a financial news analyst covering breaking corporate events for {context['company_name']}.

A material 8-K filing just hit the wire. Your institutional clients need:
1. Fast: What happened?
2. Clear: Why it matters?
3. Actionable: What should I watch?

{marking_instructions}

{item_guidance}

## OUTPUT STRUCTURE (MANDATORY)

---

### SECTION 1: EVENT SNAPSHOT

**Purpose**: Enable fast comprehension of what happened (30 seconds read)

**Format**: 2-3 short paragraphs (150-200 words total)

**Structure**:

**Paragraph 1 (Lede)**: Lead with what + who + when + how much
- Present the core facts: What event occurred? Who are the parties? 
- When did it happen? What are the key numbers?
- Identify the 8-K Item number in this paragraph

**Paragraph 2 (Details)**: Provide key terms and specifics
- Include material details: transaction structure, key terms, timing, conditions
- For M&A: deal structure, earnouts, closing timeline
- For executive changes: successor details, effective dates, background
- For financial events: amounts, terms, purpose
- For regulatory: nature of matter, potential impact

**Paragraph 3 (Context - Optional)**: Immediate significance
- Brief context if material: operational impact, strategic fit
- Only include if it adds essential context
- Skip if the details in Paragraph 2 speak for themselves

**Style**:
- News-style prose (NOT bullet points)
- Active voice, past or present tense
- Specific numbers and dates with sources [DOC: Item X.XX]
- Facts only - no speculation or analysis (save for Section 2)
- Check Exhibit 99.1 (press releases) and Exhibit 10.1 (agreements) for key details

**Quality Bar**: 
A trader can grasp the essential facts in 30 seconds while the market is open.

---

### SECTION 2: IMPACT ANALYSIS

**Purpose**: Explain why this event matters and what comes next

**Format**: Natural prose paragraphs (500-700 words)

**Structure**: Flexible and content-driven, but analyze from two key perspectives:

**Write 2-4 paragraphs with `## Subheader` format:**

Each subheader should state YOUR KEY FINDING or CONCLUSION about that dimension of impact.

---

**Analysis Framework** (use these two dimensions to guide your thinking):

**1. Internal Impact** (Impact on company operations, strategy, and financials)

How does this event affect the company's business model, operations, or financial position?

Key questions to address:
- **Strategic rationale**: Why did management do this? What problem does it solve or opportunity does it capture?
- **Financial implications**: How does this affect revenue, costs, cash flow, balance sheet? Use specific numbers [DOC:] and calculate impact if needed [CALC:]
- **Execution considerations**: What are the risks, timeline, conditions, or integration challenges?
- **Management credibility**: Track record on similar past actions

Example insight-driven headers:
- `## Deal Strengthens Core Business Model`
- `## Debt Increase Constrains Financial Flexibility`
- `## Leadership Change Creates Near-Term Uncertainty`
- `## Partnership Diversifies Revenue Base`

---

**2. External/Competitive Impact** (Impact on market position and competitive dynamics)

How does this event change the company's position in the competitive landscape?

8-K filings announce events but rarely provide the context investors need to interpret them. Your job is to provide that missing context.

Use web search to build understanding. If the filing mentions someone, find out who they are and what they've done. If it describes a transaction, understand what similar deals have looked like. If it announces an event, discover whether this is routine or remarkable in the industry.

The filing tells you what happened. Search tells you why it matters.

Key questions to address:
- **Competitive positioning**: Does this improve or weaken the company's market position?
- **Industry context**: How does this compare to peer actions or industry trends?
- **Market reaction**: What signals does this send about industry dynamics?
- **Differentiation**: Does this create or erode competitive advantages?

Example insight-driven headers:
- `## Acquisition Closes Gap with Market Leader`
- `## Partnership Follows Industry Consolidation Trend`
- `## Deal Values Company Below Peer Multiples`
- `## Move Lags Behind Competitor Actions`

---

**Application Guidelines**:

- **For simple events** (routine agreements, minor financing): Focus primarily on internal impact, add competitive context only if material
- **For major events** (M&A, large financing, CEO change): Cover both dimensions with roughly equal weight
- **For strategic events** (major partnerships, market entry): Emphasize competitive context with web search
- **Let event significance guide depth**: Not every 8-K needs extensive competitive analysis

**Quality Bar**:
Would a PM feel they understand both "what this means for the company" AND "what this means in the market"?

**CITATION REQUIREMENTS** (CRITICAL):
- Every search result MUST be cited as [1], [2], [3]
- At bottom of Section 2, list full sources with URLs when available:
  Format:
  ---
  **Sources**:
  [1] "Article Title", Source Name, Date
  [2] "Report Name", Source, Date

- NO vague references like "according to industry sources"
- If you cannot find a credible source, use [NO_DATA] rather than speculate

**Quality Bar**:
Would a PM feel confident adjusting their position based on this analysis?

---

## CRITICAL RULES

**Data Source Attribution** (MANDATORY):
- [DOC: Item X.XX] - From this 8-K filing
- [DOC: Exhibit 99.1] - From press release or other exhibits
- [CALC: formula] - Your calculations
- [1], [2], [3] - Web search results (with full citation at bottom)
- [NO_DATA] - Information not available

**Style**:
- Active voice: "Company acquired" not "was acquired by"
- Specific: "$X.XB" not "approximately X billion"
- Present/past tense for facts: "Company announced" or "Company announces"
- Adapt your analysis to the event type naturally:
  * M&A needs deal terms and strategic rationale
  * Executive changes need succession context
  * Financial events need terms and use of proceeds
  * Use your judgment as a news analyst would

**DON'T**:
- Repeat information between Section 1 and Section 2
- Speculate beyond what's disclosed
- Use marketing language: "transformative", "game-changing"
- Make up details not in the filing

---

## VISUAL ENHANCEMENT (Professional Readability)

Apply these lightweight visual markings to improve scannability:

**Three types of inline emphasis:**

1. **Yellow Highlight** (**...**):
   - Numbers and amounts: **$X.XB**, **X%**, **$X.XX**
   - Dates and timelines: **Q4 2025**, **January 15**
   - Key metrics: **Item 2.01**, **$500M transaction**

2. __Bold Text__ (__...__):
   - Key business terms: __definitive agreement__, __strategic rationale__
   - Important parties: __Target Company__, __acquiring entity__
   - Material conclusions: __significant impact__, __marks expansion__

3. *Italic Text* (*...*):
   - Cautionary language: *subject to approval*, *pending clearance*
   - Risk factors: *regulatory risk*, *execution challenge*
   - Conditional statements: *if conditions are met*, *may be adjusted*

**Structural markup:**

- Use `---` horizontal separators between major sections
- Use `## Subheader` for key discussion points in Section 2
- Example:
  ```
  ### SECTION 2: IMPACT ANALYSIS
  
  ---
  
  ## Strategic Rationale Behind the Deal
  
  The acquisition of __Target Company__ for **$2.5B** represents...
  However, *regulatory approval remains pending*...
  
  ---
  
  ## Financial Implications
  ```

**Application guidelines:**

- Section 1 (EVENT SNAPSHOT): Yellow highlights on key facts/numbers
- Section 2 (IMPACT ANALYSIS): All three types as appropriate
- Use sparingly - most text should remain plain
- Maintain professional tone throughout

---

## COMPANY CONTEXT

- **Company**: {context['company_name']} ({context['ticker']})
- **Filing Date**: {context['filing_date']}
- **Event Type**: {context.get('event_type', 'Material Event')}
- **Item**: {context.get('item_type', 'See filing')}

---

## FILING CONTENT

{content}

---

Now generate your two-section analysis following this structure.

**SECTION 1: EVENT SNAPSHOT** - 2-3 paragraphs (150-200 words)
**SECTION 2: IMPACT ANALYSIS** - Analytical prose (500-700 words)

Remember: You're a financial news analyst. Write with the urgency and precision 
of breaking news, then provide the depth of professional analysis.

---

## VISUAL ENHANCEMENT (Event Clarity Focus)

Apply these lightweight visual markings to clarify event type and materiality:

**Bold Numbers** (**...**):
- Transaction amounts: "**$4B** enterprise value"
- Key dates: "effective **December 8, 2025**"
- Material terms: "**40%** ownership retained"

**Application**:
- Section 1: Bold key numbers and amounts
- Section 2: Use all three inline emphasis types as appropriate
- Keep professional - the event itself creates urgency

Purpose: Help readers instantly identify key facts and implications.
"""
    
    def _build_s1_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """
        S-1 prompt - IPO快速筛选工具 v2.0
        核心定位：2-3分钟内判断"这个IPO是否值得深入研究"
        关键改进：观点型标题 + 压缩篇幅 + 机构背书信号化
        """
        marking_instructions = self._build_data_marking_instructions()
        
        ticker = self._get_safe_ticker(filing)
        company_name = context['company_name']
        
        return f"""You are an IPO analyst writing a screening report for retail investors.

⚠️ DATA INTEGRITY: All numbers must cite sources [DOC: section] or [NO_DATA]. Never estimate or fabricate.

Your goal: Help readers quickly decide if this IPO deserves deeper research.

Think of this as "Tinder for IPOs" - give essential information for a yes/no decision, not a complete prospectus summary.

{marking_instructions}

## CORE PRINCIPLE: Classification + Key Facts + Insight-Driven Headers

Your readers want to know:
1. **What TYPE of IPO is this?** (Growth? Value? Distressed? Concept?)
2. **What's the BEST thing about it?** (1-2 sentences)
3. **What's the BIGGEST risk?** (1-2 sentences)
4. **Who should care?** (What kind of investor)

Let the actual filing content guide what you emphasize. Each IPO tells a different story.

---

## OUTPUT STRUCTURE (MANDATORY)

**CRITICAL**: Your analysis MUST follow this exact two-section structure with proper section headers:

```
### SECTION 1: IPO SNAPSHOT
[IPO Type, Institutional Backing, Business Core, Financial Snapshot, Deal Terms]

### SECTION 2: INVESTMENT ANALYSIS
[Growth analysis, Risk analysis, Optional competitive position, Bottom Line]
```

Each section MUST start with the "### SECTION X:" header (exactly as shown).
Within each section, use thesis-driven subheaders: `## Header Text`

---

### SECTION 1: IPO SNAPSHOT
**Target Length**: 250-350 words (FIRM CAP)
**Reading Time**: 2 minutes

**Opening (MANDATORY - Always start with this)**:

## IPO Type: [Choose EXACTLY ONE from the list below - DO NOT leave blank]

**Required Categories** (choose the best match):
- High-Growth Tech (fast-growing, unprofitable)
- Profitable Value Play (profitable, stable business)
- Pre-Revenue Concept (no revenue, early stage)
- Distressed Restructuring (bankruptcy, debt restructuring)
- Passive Investment Vehicle (SPAC, fund, holding company)
- Other (specify the type if none above fit)

**CRITICAL**: You MUST select one category. If uncertain, choose "Other" and specify.

---

## Institutional Backing: [Choose EXACTLY ONE: Strong 🟢 | Neutral 🟡 | Weak 🔴]
• Underwriters: [Top-tier banks (GS/MS/JPM) OR mid-tier OR none/resale only]
• Pre-IPO investors: [Known VCs/PE with % OR strategic investors OR exiting PE]
• Signal: [1-sentence interpretation, e.g., "Top-tier validation" OR "Insider exit - caution"]

**Examples of Institutional Backing:**

Strong 🟢:
• Underwriters: Goldman Sachs, Morgan Stanley
• Pre-IPO: Sequoia Capital (18%), Andreessen Horowitz (12%)
• Signal: Top-tier institutional validation

Neutral 🟡:
• Underwriters: Mid-tier regional banks
• Pre-IPO: No major VC names disclosed
• Signal: Standard offering without standout backers

Weak 🔴:
• Underwriters: None (shareholder resale only)
• Pre-IPO: PE firms exiting via this offering
• Signal: Insider exit + no fresh capital = distress

**Example Output:**

## IPO Type: Profitable Value Play

## Institutional Backing: Strong 🟢
• Underwriters: Goldman Sachs, Morgan Stanley
• Pre-IPO investors: Digital Currency Group (DCG) controlling shareholder, Bain Capital Ventures, FirstMark Capital [DOC: Corporate Information]
• Signal: Top-tier institutional validation with strategic backing from leading blockchain-focused investors

Weak 🔴:
• Underwriters: None (shareholder resale only)
• Pre-IPO: PE firms exiting via this offering
• Signal: Insider exit + no fresh capital = distress

---

**Then cover in natural prose (NO headers needed for these)**:

**Business Core**:
What does this company do? How do they make money?
- Focus on business model ONLY
- Delete: industry background, "founded in...", market trends
- Example: "Operates SaaS platform for X, charges $Y/user/month, serves 500+ enterprise clients"

**Financial Snapshot**:
Show 2-3 year revenue trend + profitability status
- If profitable: mention margins
- If unprofitable: burn rate + runway
- Example: "Revenue grew $10M → $50M → $120M (2023-2025), still unprofitable but gross margins improved to 65%"

**Market Context** (OPTIONAL):
Include ONLY if compelling
- Large market size with growth OR unique market position
- Skip generic industry descriptions
- Example: "Targets $50B enterprise security market growing 20% annually"

---

## Deal Terms (bullet format - clean and scannable):
• Offering Size: [X shares at $Y-Z range] [DOC: Prospectus Summary]
• Expected Proceeds: [Net proceeds amount] [DOC: Use of Proceeds]
• Main Use: [Top 2 uses only, plain language] [DOC: Use of Proceeds]

---

### SECTION 2: INVESTMENT ANALYSIS
**Target Length**: 400-600 words (FIRM CAP)
**Reading Time**: 3-4 minutes

**CRITICAL: All headers must be THESIS-DRIVEN (state your findings, not just topic labels)**

---

## [Your Growth Conclusion Header]

Write a header that captures YOUR KEY FINDING about growth (3-7 words)

The header should state the growth story and financial health, not just "performance."

**Content**:
- Is growth sustainable? What's driving it?
- Customer metrics, retention, expansion plans [DOC: MD&A, Business]
- Profitability path if unprofitable
- Cite specific numbers with [DOC: source]

---

## [Your Risk Conclusion Header]

Write a header that captures YOUR KEY RISK FINDING (3-7 words)

The header should name the specific critical risks, not just "risks."

**Content**:
Focus on 2-3 DEAL-BREAKER risks only

What's a deal-breaker risk?
- Would make you NOT invest
- Examples: Going concern, >40% revenue concentration, existential regulatory threat, insider mass exit

What to SKIP:
- Generic risks every company has ("competition exists", "macro uncertainty")
- Minor operational risks
- Standard disclosures

**Format for each risk**:
1. State it clearly in one sentence
2. Explain the impact (why it matters)
3. Cite source [DOC: Risk Factors]

---

## [Your Competitive Position Header - OPTIONAL]

Include ONLY if there's something material to say:
- Unique moat or clear differentiation
- Specific market share data
- Skip generic competition sections

**Content**:
- Unique competitive advantages with evidence
- Market position vs. public comparables
- Cite [DOC: Business] or [1], [2] if using external data

---

## Bottom Line

**Content**:
Synthesize the key takeaway: IPO type, main strength, main weakness, and who should care.

---

## FORMATTING RULES (Readability First)

**Header Format**:
- Use: `## Header Text` for subheaders
- Keep headers SHORT: 3-7 words
- Headers must be CONCLUSIONS (what you found), not labels (what section this is)
- Be specific: include numbers or concrete terms when possible

**Visual Marking** (use the three inline emphasis types):
- **Yellow highlight** for numbers: **$500M**, **45%**
- __Bold text__ for key concepts: __unique moat__, __market leader__
- *Italic text* for risks: *going concern*, *concentration risk*

---

## CRITICAL RULES

**Length Discipline** (ABSOLUTE):
- Section 1: 250-350 words MAX
- Section 2: 400-600 words MAX
- If approaching limit: Cut weaker points, don't compress language

**Content Focus: Decision-Relevant Only**

Every sentence should help investors decide: "Should I research this IPO deeper?"

Include what matters:
- How they make money + who pays them
- Financial trajectory: growth trend + profitability/burn status
- 2-3 deal-breaker risks (would stop investment)
- Quality signals (backing, unique moats if material)

Ruthlessly cut:
- Background that doesn't explain THIS company's specific performance
- Generic risks or statements that apply to any company
- Details irrelevant to the investment decision

**What to AVOID**:
- Investment recommendations ("good IPO", "buy", "suitable for aggressive investors")
- Hype language ("disruptive", "revolutionary", "innovative", "transformative")
- Speculation beyond filing disclosures

**Style**:
- Active voice, specific numbers, plain language
- Write like a smart analyst, not a prospectus

---

## COMPANY CONTEXT

- **Company**: {company_name}
- **Ticker**: {ticker} (or "Pre-IPO" if not assigned yet)
- **Filing Date**: {context['filing_date']}

---

## FILING CONTENT

{content}

---

Now generate your two-section analysis:

**SECTION 1: IPO SNAPSHOT** - Type + backing + core facts (250-350 words)
**SECTION 2: INVESTMENT ANALYSIS** - Growth + risks + bottom line with INSIGHT-DRIVEN headers (400-600 words)

Remember: 
- This is a SCREENING TOOL, not a prospectus rewrite
- Headers should be YOUR CONCLUSIONS, not generic labels
- Focus on decision-relevant information only
- Be ruthless about cutting non-essential content
"""
    
    def _build_generic_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Generic prompt"""
        marking_instructions = self._build_data_marking_instructions()
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""You are a financial analyst examining this {filing_type_value} for {context['company_name']}.

{marking_instructions}

Identify key disclosures and their significance with proper citations.

FILING CONTENT:
{content}"""
    
    async def _generate_text_with_search(self, prompt: str, max_tokens: int = 500) -> Tuple[str, List[Dict]]:
        """Generate text with web search support using o3-mini"""
        try:
            response = client.chat.completions.create(
                model=self.model,  # Now using o3-mini
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a professional financial analyst. You have web search access to enrich analysis with industry context."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content.strip()
            
            annotations = getattr(response.choices[0].message, 'annotations', None) or []
            references = self._process_citations(content, annotations)
            
            return content, references
            
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            return "", []
    
    def _process_citations(self, content: str, annotations: List) -> List[Dict]:
        """Process OpenAI annotations into references"""
        if not annotations:
            return []
        
        references = []
        url_to_id = {}
        
        for idx, annotation in enumerate(annotations, start=1):
            if hasattr(annotation, 'url_citation'):
                url_citation = annotation.url_citation
                url = url_citation.url
                title = url_citation.title if hasattr(url_citation, 'title') else "Source"
                
                if url not in url_to_id:
                    url_to_id[url] = idx
                    references.append({
                        'id': idx,
                        'title': title,
                        'url': url
                    })
        
        logger.info(f"Processed {len(references)} web search references")
        return references
    
    async def _generate_feed_summary_from_unified(self, unified_analysis: str, filing_type: str, filing: Filing) -> str:
        """
        Generate feed summary with words-based approach
        v11_o3mini: Ticker-first, 3-sentence structure, flexible third sentence
        """
        ticker = self._get_safe_ticker(filing)
        
        # Build filing-type specific prompt with words-based constraints
        if filing_type in ["FORM_10Q", "10-Q"]:
            max_tokens = 80
            prompt = f"""{FEED_SUMMARY_GUIDELINES}

YOUR MISSION: Write a 3-sentence earnings alert.

STRUCTURE (3 sentences, 30-50 words total):
Sentence 1: Headline - Did {ticker} beat/miss? Key metrics (revenue/EPS)
Sentence 2: Driver - What caused it? Be specific but concise
Sentence 3: Implication - What does it mean? (outlook/momentum/concern)

Focus: Tell the earnings story clearly and completely.

Analysis excerpt:
{unified_analysis[:1000]}

Write your 3-sentence alert (30-50 words):"""

        elif filing_type in ["FORM_10K", "10-K"]:
            max_tokens = 80
            prompt = f"""{FEED_SUMMARY_GUIDELINES}

YOUR MISSION: Write a 3-sentence annual summary.

STRUCTURE (3 sentences, 30-50 words total):
Sentence 1: Full-year headline - Growth/performance vs prior year
Sentence 2: Key driver - What powered results or held them back
Sentence 3: Forward look - Guidance or strategic direction

Focus: Capture the year in three clear points.

Analysis excerpt:
{unified_analysis[:1000]}

Write your 3-sentence summary (30-50 words):"""

        elif filing_type in ["FORM_8K", "8-K"]:
            max_tokens = 70
            prompt = f"""{FEED_SUMMARY_GUIDELINES}

YOUR MISSION: Write a 2-3 sentence event alert.

STRUCTURE (2-3 sentences, 25-45 words total):
Sentence 1: What happened (the event)
Sentence 2: Key detail or scale
Sentence 3 (if needed): Business impact

Be flexible - use 2 sentences if event is simple, 3 if complex.

Analysis excerpt:
{unified_analysis[:800]}

Write your alert (25-45 words):"""

        elif filing_type in ["FORM_S1", "S-1"]:
            max_tokens = 85
            prompt = f"""{FEED_SUMMARY_GUIDELINES}

YOUR MISSION: Write a 3-sentence IPO preview.

STRUCTURE (3 sentences, 35-55 words total):
Sentence 1: What the company does (business model)
Sentence 2: Market opportunity or traction (why it matters)
Sentence 3: Offering details (size/use of proceeds)

Focus: Help investors decide if they want to dig deeper.

Analysis excerpt:
{unified_analysis[:1000]}

Write your 3-sentence preview (35-55 words):"""

        else:
            # Generic filing
            max_tokens = 70
            prompt = f"""{FEED_SUMMARY_GUIDELINES}

YOUR MISSION: Write a 2-3 sentence filing summary.

STRUCTURE (2-3 sentences, 25-40 words total):
Sentence 1: What the filing is about
Sentence 2: Key takeaway or implication
Sentence 3 (if needed): Additional context

Analysis excerpt:
{unified_analysis[:1000]}

Write your summary (25-40 words):"""
        
        # Generate summary
        summary, _ = await self._generate_text_with_search(prompt, max_tokens=max_tokens)
        
        # Clean up any remaining source citations
        summary = re.sub(r'\[DOC:[^\]]+\]', '', summary)
        summary = re.sub(r'\[\d+\]', '', summary)
        summary = re.sub(r'\[FMP\]', '', summary)
        summary = re.sub(r'\[CALC:[^\]]+\]', '', summary)
        summary = re.sub(r'\s+', ' ', summary).strip()
        
        # Word count validation (soft limit - log warning if exceeded)
        word_count = len(summary.split())
        max_words_map = {
            "FORM_10Q": 50,
            "10-Q": 50,
            "FORM_10K": 50,
            "10-K": 50,
            "FORM_8K": 45,
            "8-K": 45,
            "FORM_S1": 55,
            "S-1": 55
        }
        max_words = max_words_map.get(filing_type, 50)
        
        if word_count > max_words + 5:  # Allow 5-word buffer
            logger.warning(f"Summary exceeds word limit: {word_count} words (max: {max_words})")
        
        logger.info(f"Generated feed summary ({word_count} words): {summary[:100]}...")
        
        return summary

    def _extract_markup_data(self, text: str) -> Dict:
        """Extract markup metadata"""
        markup_data = {
            'numbers': [],
            'concepts': [],
            'positive': [],
            'negative': [],
            'sections': [],
            'sources': []
        }
        
        sections = re.findall(r'^##\s+(.+)', text, re.MULTILINE)
        markup_data['sections'] = sections
        
        numbers = re.findall(r'\*([^*]+)\*', text)
        markup_data['numbers'] = numbers[:10]
        
        concepts = re.findall(r'\*\*([^*]+)\*\*', text)
        markup_data['concepts'] = concepts[:8]
        
        for pattern_name, pattern in DATA_SOURCE_PATTERNS.items():
            matches = re.findall(pattern, text)
            for match in matches[:5]:
                markup_data['sources'].append({
                    'type': pattern_name,
                    'reference': str(match) if not isinstance(match, str) else match
                })
        
        return markup_data
    
    def _optimize_markup_density(self, text: str) -> str:
        """Monitor markup density"""
        total_length = len(text)
        
        markup_patterns = [
            r'\*[^*]+\*',
            r'\*\*[^*]+\*\*',
        ]
        markup_patterns.extend(DATA_SOURCE_PATTERNS.values())
        
        markup_chars = 0
        for pattern in markup_patterns:
            matches = re.findall(pattern, text)
            markup_chars += sum(len(str(match)) for match in matches)
        
        density = markup_chars / total_length if total_length > 0 else 0
        logger.info(f"Markup density: {density:.2%}")
        
        return text
    
    async def _extract_supplementary_fields(self, filing: Filing, unified_result: Dict, primary_content: str, full_text: str):
        """Extract supplementary fields"""
        unified_text = unified_result['unified_analysis']
        ticker = self._get_safe_ticker(filing)
        
        # Get official Items from filing.event_items (populated by edgar_scanner)
        official_items = filing.event_items if filing.event_items else None
        
        filing.key_tags = self._generate_enhanced_tags(
            unified_result['markup_data'], 
            unified_text, 
            filing.filing_type, 
            ticker,
            official_items=official_items
        )
        
        filing.management_tone = None
        filing.tone_explanation = None
        filing.key_questions = []
        filing.financial_highlights = None
        filing.ai_summary = None
        
        if filing.filing_type == FilingType.FORM_8K:
            filing.event_type = self._identify_8k_event_type(primary_content, official_items=official_items)
            filing.item_type = self._extract_8k_item_type(primary_content)
    
    def _generate_enhanced_tags(self, markup_data: Dict, unified_text: str, filing_type: Union[FilingType, str], ticker: str, official_items: List[str] = None) -> List[str]:
        """
        Generate intelligent, context-aware tags from filing analysis
        Strategy: Extract meaningful business/event/financial characteristics, not generic categories
        ENHANCED: Use official SEC Item numbers for 8-K tags when available
        """
        tags = []
        text_lower = unified_text.lower()
        filing_type_key = self._get_safe_filing_type_value(filing_type) if not isinstance(filing_type, str) else filing_type
        
        # === LAYER 1: Business Model & Technology Tags (Specific, not generic) ===
        business_patterns = {
            # AI & Advanced Tech
            'AI Platform': ['artificial intelligence', 'machine learning', 'ai-driven', 'ai platform', 'neural network'],
            'Generative AI': ['generative ai', 'large language model', 'llm', 'gpt', 'chatbot'],
            'Cloud Infrastructure': ['cloud infrastructure', 'data center', 'aws', 'azure', 'serverless'],
            'SaaS': ['software as a service', 'saas', 'subscription software', 'recurring revenue'],
            'Cybersecurity': ['cybersecurity', 'threat detection', 'zero trust', 'endpoint security'],
            
            # Healthcare & Biotech
            'Biotech': ['biotech', 'biologics', 'gene therapy', 'cell therapy', 'monoclonal antibody'],
            'Medical Device': ['medical device', 'imaging system', 'diagnostic equipment', 'surgical robot'],
            'Digital Health': ['telehealth', 'remote patient', 'digital therapeutics', 'health tech'],
            'Clinical Stage': ['clinical trial', 'phase 2', 'phase 3', 'fda approval', 'regulatory submission'],
            
            # Fintech & Financial Services
            'Fintech': ['fintech', 'digital payment', 'payment processing', 'neobank'],
            'Crypto/Blockchain': ['cryptocurrency', 'blockchain', 'bitcoin', 'crypto exchange', 'digital asset'],
            'Banking': ['commercial bank', 'retail bank', 'lending', 'deposit', 'net interest'],
            
            # Consumer & Retail
            'E-commerce': ['e-commerce', 'online retail', 'marketplace', 'direct-to-consumer', 'd2c'],
            'Consumer Brand': ['consumer brand', 'brand portfolio', 'cpg', 'consumer packaged'],
            
            # Energy & Sustainability
            'Clean Energy': ['solar', 'wind energy', 'renewable', 'battery storage', 'clean energy'],
            'EV/Mobility': ['electric vehicle', 'ev maker', 'autonomous', 'self-driving', 'battery technology'],
            
            # Industrial & Manufacturing
            'Semiconductor': ['semiconductor', 'chip design', 'wafer fabrication', 'foundry'],
            'Aerospace': ['aerospace', 'defense contractor', 'satellite', 'aviation'],
        }
        
        for tag_name, keywords in business_patterns.items():
            if any(keyword in text_lower for keyword in keywords):
                tags.append(tag_name)
                if len(tags) >= 2:  # Limit business tags to 2
                    break
        
        # === LAYER 2: Event-Specific Tags (8-K focus) ===
        if filing_type_key in ['FORM_8K', '8-K']:
            # ENHANCED: Use official SEC Item definitions if available
            if official_items:
                guidance = self._get_official_item_guidance(official_items)
                suggested_tags = guidance.get('suggested_tags', [])
                tags.extend(suggested_tags)
                logger.debug(f"Using official Item tags: {suggested_tags}")
            else:
                # Fallback: keyword-based detection
                event_patterns = {
                    'Executive Change': ['ceo', 'chief executive', 'president', 'appoint', 'resign', 'transition'],
                    'M&A Deal': ['merger', 'acquisition', 'acquire', 'definitive agreement', 'purchase agreement'],
                    'Earnings Release': ['financial results', 'quarter ended', 'net income', 'revenue', 'earnings per share'],
                    'Restructuring': ['restructuring', 'cost reduction', 'workforce reduction', 'impairment', 'facility closure'],
                    'Financing': ['credit facility', 'loan agreement', 'senior notes', 'debt offering', 'equity offering'],
                    'Partnership': ['strategic partnership', 'collaboration', 'joint venture', 'licensing agreement'],
                    'Regulatory': ['fda', 'regulatory approval', 'compliance', 'investigation', 'settlement'],
                }
                
                for event_tag, keywords in event_patterns.items():
                    if any(keyword in text_lower for keyword in keywords):
                        tags.append(event_tag)
                        break  # Only one event tag
        
        # === LAYER 3: Financial Performance Tags (10-Q/10-K focus) ===
        if filing_type_key in ['FORM_10Q', '10-Q', 'FORM_10K', '10-K']:
            performance_patterns = {
                'Revenue Beat': ['revenue beat', 'revenue exceeded', 'revenue above', 'beat estimate'],
                'Revenue Miss': ['revenue miss', 'revenue below', 'revenue declined', 'missed estimate'],
                'Guidance Raised': ['raised guidance', 'increased outlook', 'upgraded forecast', 'raised full-year'],
                'Guidance Cut': ['lowered guidance', 'reduced outlook', 'cut forecast', 'revised down'],
                'Margin Expansion': ['margin expansion', 'margin improvement', 'operating margin increased', 'gross margin up'],
                'Cost Pressure': ['cost pressure', 'margin compression', 'headwinds', 'expense growth', 'margin decline'],
                'Profitable': ['net income', 'profitable', 'positive earnings', 'profit margin'],
                'Loss-Making': ['net loss', 'operating loss', 'unprofitable', 'negative earnings'],
            }
            
            for perf_tag, keywords in performance_patterns.items():
                if any(keyword in text_lower for keyword in keywords):
                    tags.append(perf_tag)
                    if len([t for t in tags if t in performance_patterns.keys()]) >= 2:
                        break  # Max 2 performance tags
        
        # === LAYER 4: IPO Characteristics (S-1 focus) ===
        if filing_type_key in ['FORM_S1', 'S-1']:
            ipo_patterns = {
                'Pre-Revenue': ['pre-revenue', 'no revenue', 'minimal revenue', 'early stage'],
                'High Growth': ['rapid growth', 'high growth', 'growth rate', 'yoy growth'],
                'Profitable IPO': ['profitable', 'positive earnings', 'net income'],
                'Mega Raise': ['raise', 'offering', 'ipo'],  # Will check amount separately
            }
            
            for ipo_tag, keywords in ipo_patterns.items():
                if any(keyword in text_lower for keyword in keywords):
                    tags.append(ipo_tag)
            
            # Check for large offering amount
            import re
            amount_matches = re.findall(r'\$(\d+(?:,\d+)?(?:\.\d+)?)\s*(million|billion)', text_lower)
            if amount_matches:
                try:
                    for amount_str, unit in amount_matches:
                        amount = float(amount_str.replace(',', ''))
                        if unit == 'billion' or (unit == 'million' and amount >= 100):
                            tags.append('$100M+ Raise')
                            break
                except:
                    pass
        
        # === LAYER 5: Extract Key Concepts from Markup Data ===
        if markup_data and 'concepts' in markup_data and markup_data['concepts']:
            # Extract 1-2 meaningful concepts that aren't generic words
            generic_words = {'revenue', 'growth', 'company', 'business', 'quarter', 'year', 'increase', 'decrease'}
            for concept in markup_data['concepts'][:5]:
                concept_clean = str(concept).strip().title()
                if (concept_clean.lower() not in generic_words and 
                    len(concept_clean) > 3 and 
                    concept_clean not in tags):
                    tags.append(concept_clean)
                    if len([t for t in tags if t.istitle()]) >= 1:  # Max 1 extracted concept
                        break
        
        # === FINAL: Deduplicate and limit to 5 tags ===
        tags = list(dict.fromkeys(tags))[:5]
        
        logger.info(f"Generated enhanced tags for {ticker}: {tags}")
        return tags
    
    def _get_official_item_guidance(self, official_items: List[str]) -> Dict:
        """
        Get official SEC Item guidance for 8-K classification
        
        Args:
            official_items: List of Item numbers from RSS (e.g., ["2.03", "9.01"])
            
        Returns:
            Dict with Item guidance including category, description, focus areas, and tags
        """
        if not official_items:
            # No official Item provided
            return {
                'item_number': None,
                'title': 'Corporate Event',
                'category': 'Other Corporate Event',
                'description': 'Material corporate event - details to be determined from document content',
                'focus_areas': ['event description', 'parties involved', 'key terms', 'significance'],
                'suggested_tags': ['Corporate Event']
            }
        
        # Filter out 9.01 (Exhibits - not a substantive event)
        substantive_items = [item for item in official_items if not item.startswith('9.')]
        
        if not substantive_items:
            # Only exhibits, no substantive items
            return {
                'item_number': official_items[0],
                'title': 'Financial Statements and Exhibits',
                'category': 'Exhibits Only',
                'description': 'Filing contains exhibits without substantive event disclosure',
                'focus_areas': ['exhibits listed'],
                'suggested_tags': ['Corporate Event']
            }
        
        # Take the first substantive Item as primary
        primary_item = substantive_items[0]
        
        # Look up official definition
        item_def = SEC_ITEM_DEFINITIONS.get(primary_item)
        
        if item_def:
            # Found official definition
            result = {
                'item_number': primary_item,
                'title': item_def['title'],
                'category': item_def['category'],
                'description': item_def['description'],
                'focus_areas': item_def['focus_areas'],
                'suggested_tags': item_def['suggested_tags']
            }
            
            # If multiple substantive items, note them
            if len(substantive_items) > 1:
                result['additional_items'] = substantive_items[1:]
                logger.info(f"Multiple Items detected: primary={primary_item}, additional={substantive_items[1:]}")
            
            logger.info(f"✅ Using official Item {primary_item}: {item_def['title']}")
            return result
        else:
            # Unknown Item number (rare)
            logger.warning(f"Unknown Item number: {primary_item}")
            return {
                'item_number': primary_item,
                'title': f'Item {primary_item}',
                'category': 'Other Corporate Event',
                'description': 'Refer to document for event details (uncommon Item type)',
                'focus_areas': ['event description', 'key terms', 'significance'],
                'suggested_tags': ['Corporate Event']
            }
    
    def _identify_8k_event_type(self, content: str, official_items: List[str] = None) -> str:
        """
        Identify 8-K event type using official Item numbers when available
        
        Args:
            content: Filing content
            official_items: Official Item numbers from RSS (e.g., ["2.03", "9.01"])
            
        Returns:
            Event type description
        """
        # If we have official Items, use them
        if official_items:
            guidance = self._get_official_item_guidance(official_items)
            return guidance['title']  # Return official SEC title
        
        # Fallback: extract from content
        content_lower = content.lower()
        item_pattern = r'item\s+(\d+\.\d+)'
        items_in_content = re.findall(item_pattern, content_lower)
        
        if items_in_content:
            # Found Items in content, use first one
            guidance = self._get_official_item_guidance(items_in_content)
            return guidance['title']
        
        # Last resort: keyword-based detection
        if 'item 2.02' in content_lower or 'results of operations' in content_lower:
            return "Earnings Release"
        elif 'item 1.01' in content_lower:
            return "Material Agreement"
        elif 'item 5.02' in content_lower:
            return "Executive/Board Change"
        elif 'item 2.03' in content_lower:
            return "Financing Event"
        else:
            return "Corporate Event"
    
    def _extract_8k_item_type(self, content: str) -> Optional[str]:
        """Extract 8-K item number"""
        item_pattern = r'Item\s+(\d+\.\d+)'
        match = re.search(item_pattern, content, re.IGNORECASE)
        return match.group(1) if match else None


# Initialize singleton
ai_processor = AIProcessor()