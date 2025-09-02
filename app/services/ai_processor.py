# app/services/ai_processor.py
"""
AI Processor Service - Enhanced with Data Accuracy Constraints
STREAMLINED: Focused on core functionality only
- Unified Analysis generation (main content)
- Feed Summary extraction (list view)  
- Smart Markup Data (frontend rendering)
- Enhanced Tags (intelligent categorization)

REMOVED: Question generation, tone analysis, separate financial highlights
ENHANCED: Management analysis, S-1 processing, tag quality
REVOLUTIONARY: Enhanced data source marking and Markdown table processing to prevent hallucination
FIXED: Added defensive type checking for FilingType to prevent 'str' object has no attribute 'value' errors
UPDATED: Added FMP company profile data fetching and storage during AI processing
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

# ENHANCED Data source marking patterns - CRITICAL for accuracy
DATA_SOURCE_PATTERNS = {
    'document': r'\[DOC:\s*([^\]]+)\]',
    'api': r'\[API:\s*([^\]]+)\]',
    'calc': r'\[CALC:\s*([^\]]+)\]',
    'no_data': r'\[NO_DATA\]',
    'caution': r'\[CAUTION\]'
}

class AIProcessor:
    """
    Process filings using OpenAI with enhanced management analysis and tag extraction
    REVOLUTIONARY: Enhanced with Markdown table processing and strict data accuracy constraints
    FIXED: Added defensive FilingType handling to prevent attribute errors
    UPDATED: Added FMP company profile data integration
    """
    
    def __init__(self):
        self.model = settings.AI_MODEL
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        
        # Initialize tokenizer
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Token limits
        self.max_input_tokens = 100000
        self.target_output_tokens = 3000
    
    def _get_safe_filing_type_value(self, filing_type: Union[FilingType, str]) -> str:
        """
        FIXED: Safely get filing type value, handling both enum and string types
        This prevents the 'str' object has no attribute 'value' error
        """
        if isinstance(filing_type, str):
            return filing_type
        elif hasattr(filing_type, 'value'):
            return filing_type.value
        elif isinstance(filing_type, FilingType):
            return filing_type.value
        else:
            logger.warning(f"Unexpected filing_type type: {type(filing_type)}, value: {filing_type}")
            return str(filing_type)
    
    def _get_safe_ticker(self, filing: Filing) -> str:
        """Get ticker safely, returning a default value if None"""
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
        """Count tokens in text using tiktoken"""
        try:
            return len(self.encoding.encode(text))
        except:
            return len(text) // 4
    
    def _validate_data_marking(self, text: str) -> Tuple[bool, List[str]]:
        """
        CRITICAL: Validate that AI output contains proper data source markings
        This prevents the hallucination issues identified in the solution document
        """
        issues = []
        
        # Extract all numbers and claims
        numbers = re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', text)
        
        # Check if numbers have nearby citations - ENHANCED logic
        unmarked_numbers = 0
        for number in numbers[:15]:  # Check more numbers
            pos = text.find(number)
            if pos == -1:
                continue
                
            # Expand search window for citations
            nearby_text = text[max(0, pos-100):pos+100]
            has_citation = any(
                re.search(pattern, nearby_text) 
                for pattern in DATA_SOURCE_PATTERNS.values()
            )
            
            if not has_citation:
                unmarked_numbers += 1
                if unmarked_numbers <= 3:  # Only log first few
                    issues.append(f"Unmarked number: {number}")
        
        # Check for forbidden phrases when NO_DATA should be used
        if '[NO_DATA]' not in text:
            forbidden_without_data = [
                'analyst consensus', 'analyst expectations', 'analyst estimate',
                'beat expectations', 'missed estimates', 'exceeded analyst',
                'below analyst', 'vs consensus', 'consensus view'
            ]
            for phrase in forbidden_without_data:
                if phrase.lower() in text.lower():
                    if not re.search(r'\[API:\s*FMP\]', text):
                        issues.append(f"Used '{phrase}' without analyst data or [NO_DATA] marker")
        
        # Check minimum marking density - ENHANCED
        total_markings = sum(
            len(re.findall(pattern, text)) 
            for pattern in DATA_SOURCE_PATTERNS.values()
        )
        
        text_length = len(text)
        if text_length > 1000:
            expected_markings = max(5, text_length // 500)  # At least 1 marking per 500 chars
            if total_markings < expected_markings:
                issues.append(f"Insufficient data source markings: {total_markings}/{expected_markings} expected")
        
        # Check for template/placeholder content
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
        """
        Intelligently truncate content while preserving key sections
        FIXED: Added safe filing type handling
        """
        current_tokens = self._count_tokens(content)
        
        if current_tokens <= max_tokens:
            return content
        
        logger.info(f"Content needs truncation: {current_tokens} tokens > {max_tokens} limit")
        
        # Split content into sections
        sections = content.split('\n\n')
        
        # FIXED: Get filing type value safely
        filing_type_value = self._get_safe_filing_type_value(filing_type)
        
        # Priority keywords for different filing types
        priority_keywords = {
            'FORM_10K': ['management discussion', 'financial statements', 'risk factors', 'business', 'management', 'executive', 'compensation'],
            'FORM_10Q': ['financial statements', 'management discussion', 'quarter', 'three months', 'management', 'outlook'],
            'FORM_8K': ['item', 'event', 'agreement', 'announcement', 'exhibit 99', 'management', 'executive'],
            'FORM_S1': ['summary', 'risk factors', 'use of proceeds', 'business', 'management', 'underwriting', 'competitive']
        }
        
        # Score each section
        scored_sections = []
        filing_keywords = priority_keywords.get(filing_type_value, [])
        
        for section in sections:
            score = 0
            section_lower = section.lower()
            
            # Score based on keywords
            for keyword in filing_keywords:
                if keyword in section_lower:
                    score += 10
            
            # ENHANCED: Prioritize Markdown tables (from enhanced text_extractor)
            if '|' in section and '---' in section:
                score += 20  # High priority for structured tables
            
            # Score based on financial data
            score += len(re.findall(r'\$[\d,]+', section)) * 2
            score += len(re.findall(r'\d+\.?\d*%', section)) * 2
            
            # Bonus for management-related content
            if any(term in section_lower for term in ['management', 'executive', 'ceo', 'cfo', 'board']):
                score += 15
            
            # Bonus for enhanced markdown formatting
            score += len(re.findall(r'\*\*[^*]+\*\*', section)) * 1  # Bold text
            
            scored_sections.append((score, section))
        
        # Sort by score
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        
        # Build truncated content
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
        """Process a filing using unified AI analysis with enhanced management focus"""
        try:
            # Update status
            filing.status = ProcessingStatus.ANALYZING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            ticker = self._get_safe_ticker(filing)
            company_name = filing.company.name if filing.company else "Unknown Company"
            
            # FIXED: Use safe filing type access
            filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
            logger.info(f"Starting enhanced AI processing for {ticker} {filing_type_value}")
            
            # NEW: Fetch and store FMP company profile data if applicable
            await self._fetch_and_store_fmp_data(db, filing, ticker)
            
            # Get filing directory
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            
            # Extract text with ENHANCED Markdown support
            sections = text_extractor.extract_from_filing(filing_dir)
            
            if 'error' in sections:
                raise Exception(f"Text extraction failed: {sections['error']}")
            
            extracted_filing_type = sections.get('filing_type', 'UNKNOWN')
            logger.info(f"Extracted filing type: {extracted_filing_type}")
            
            # REVOLUTIONARY: Use enhanced_text (Markdown) if available, fallback to primary_content
            primary_content = sections.get('enhanced_text', '') or sections.get('primary_content', '')
            full_text = sections.get('full_text', '')
            
            # Log the content type being used
            if sections.get('enhanced_text'):
                logger.info(f"Using enhanced Markdown content: {len(primary_content)} chars")
            else:
                logger.info(f"Using standard primary content: {len(primary_content)} chars")
            
            if filing.filing_type == FilingType.FORM_8K and 'exhibit_99_content' in sections:
                logger.info(f"8-K includes Exhibit 99 content: {len(sections['exhibit_99_content'])} chars")
            
            if not primary_content or len(primary_content) < 100:
                raise Exception("Insufficient text content extracted")
            
            logger.info(f"Extracted content - Primary: {len(primary_content)} chars, Full: {len(full_text)} chars")
            
            # Get analyst expectations for 10-Q if enabled
            analyst_data = None
            if filing.filing_type == FilingType.FORM_10Q and settings.ENABLE_EXPECTATIONS_COMPARISON and settings.FMP_ENABLE:
                if ticker and ticker not in ["UNKNOWN", "PRE-IPO"] and not ticker.startswith("CIK"):
                    logger.info(f"[AI Processor] Fetching analyst expectations from FMP for {ticker}")
                    
                    target_date = None
                    if filing.period_end_date:
                        target_date = filing.period_end_date.strftime('%Y-%m-%d')
                        logger.info(f"[AI Processor] Using period end date {target_date} to fetch expectations")
                    elif filing.filing_date:
                        target_date = filing.filing_date.strftime('%Y-%m-%d')
                        logger.info(f"[AI Processor] Using filing date {target_date} to fetch expectations (fallback)")
                    
                    analyst_data = fmp_service.get_analyst_estimates(
                        ticker,
                        target_date=target_date
                    )
                    
                    if analyst_data:
                        logger.info(f"[AI Processor] Retrieved analyst expectations from FMP for {ticker}")
                    else:
                        logger.info(f"[AI Processor] No analyst expectations available from FMP for {ticker}")
            
            # Generate unified analysis with intelligent retry
            unified_result = await self._generate_unified_analysis_with_retry(
                filing, primary_content, full_text, analyst_data
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.analysis_version = "v7_enhanced_fmp"  # Updated version marker
            
            if analyst_data:
                filing.analyst_expectations = analyst_data
            
            # Extract supplementary fields
            await self._extract_supplementary_fields(filing, unified_result, primary_content, full_text)
            
            # Set status
            filing.status = ProcessingStatus.COMPLETED
            filing.processing_completed_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"✅ Enhanced AI processing completed for {filing.accession_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error in enhanced AI processing: {e}")
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            return False
    
    async def _fetch_and_store_fmp_data(self, db: Session, filing: Filing, ticker: str):
        """
        NEW: Fetch FMP company profile data and store in database during AI processing
        This implements the core optimization from the FMP API optimization report
        """
        # Only fetch for companies with valid tickers (exclude IPO and unknown companies)
        if not ticker or ticker in ["UNKNOWN", "PRE-IPO"] or ticker.startswith("CIK"):
            logger.info(f"[FMP Integration] Skipping FMP data fetch for {ticker} - invalid ticker")
            return
        
        # Only fetch if we don't have recent FMP data (avoid redundant API calls)
        company = filing.company
        if not company:
            logger.warning(f"[FMP Integration] No company object for filing {filing.accession_number}")
            return
        
        # Check if we need to fetch FMP data (if key fields are missing or stale)
        needs_fmp_data = (
            not company.market_cap or 
            not company.pe_ratio or 
            not company.website
        )
        
        if not needs_fmp_data:
            logger.info(f"[FMP Integration] Company {ticker} already has FMP data, skipping fetch")
            return
        
        try:
            logger.info(f"[FMP Integration] Fetching company profile from FMP for {ticker}")
            fmp_data = fmp_service.get_company_profile(ticker)
            
            if fmp_data:
                logger.info(f"[FMP Integration] Successfully retrieved FMP data for {ticker}")
                
                # Extract the data we need (market_cap, pe_ratio, website)
                company_updates = {}
                
                # Market cap (convert from FMP format to millions)
                if fmp_data.get('market_cap'):
                    company_updates['market_cap'] = fmp_data['market_cap'] / 1e6  # Convert to millions
                    logger.info(f"[FMP Integration] Updated market cap: ${company_updates['market_cap']:.0f}M")
                
                # Website
                if fmp_data.get('website'):
                    company_updates['website'] = fmp_data['website']
                    logger.info(f"[FMP Integration] Updated website: {company_updates['website']}")
                
                # Get PE ratio from key metrics if not in profile
                pe_ratio = fmp_data.get('pe_ratio')
                if not pe_ratio:
                    # Try to get PE ratio from key metrics
                    key_metrics = fmp_service.get_company_key_metrics(ticker)
                    if key_metrics and key_metrics.get('pe_ratio'):
                        pe_ratio = key_metrics['pe_ratio']
                
                if pe_ratio and pe_ratio > 0:
                    company_updates['pe_ratio'] = pe_ratio
                    logger.info(f"[FMP Integration] Updated PE ratio: {pe_ratio:.1f}")
                
                # Update company fields directly
                for field, value in company_updates.items():
                    setattr(company, field, value)
                
                # Also update other useful fields if they're empty
                if fmp_data.get('sector') and not company.sector:
                    company.sector = fmp_data['sector']
                
                if fmp_data.get('industry') and not company.industry:
                    company.industry = fmp_data['industry']
                
                if fmp_data.get('employees') and not company.employees:
                    company.employees = fmp_data['employees']
                
                if fmp_data.get('headquarters') and not company.headquarters:
                    company.headquarters = fmp_data['headquarters']
                
                # Mark that we've updated the company
                company.updated_at = datetime.utcnow()
                
                logger.info(f"[FMP Integration] Successfully updated company {ticker} with FMP data")
                
            else:
                logger.warning(f"[FMP Integration] No FMP data available for {ticker}")
                
        except Exception as e:
            logger.error(f"[FMP Integration] Error fetching FMP data for {ticker}: {e}")
            # Don't fail the entire processing if FMP fetch fails
            pass
    
    async def _generate_unified_analysis_with_retry(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str,
        analyst_data: Optional[Dict] = None
    ) -> Dict:
        """Generate unified analysis with intelligent retry logic and enhanced validation"""
        max_retries = 3
        
        for attempt in range(max_retries):
            logger.info(f"Analysis attempt {attempt + 1}/{max_retries}")
            
            # Preprocess content
            processed_content = self._preprocess_content_for_ai(
                primary_content, full_text, filing.filing_type, attempt
            )
            
            # Generate analysis
            unified_result = await self._generate_unified_analysis(
                filing, processed_content, processed_content, analyst_data
            )
            
            # CRITICAL: Validate data marking
            is_valid, validation_issues = self._validate_data_marking(unified_result['unified_analysis'])
            
            if not is_valid:
                logger.warning(f"Data marking validation failed (attempt {attempt + 1}): {validation_issues}")
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(f"Data marking validation failed after {max_retries} attempts: {validation_issues}")
            
            # Validate word count
            word_count = len(unified_result['unified_analysis'].split())
            
            # Flexible minimums based on filing type
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
            
            # Check for template numbers
            if self._contains_template_numbers(unified_result['unified_analysis']):
                logger.warning(f"Template numbers detected, retrying... (attempt {attempt + 1})")
                continue
            
            # Check content quality
            if not self._validate_content_quality(unified_result['unified_analysis'], filing.filing_type):
                logger.warning(f"Content quality check failed, retrying... (attempt {attempt + 1})")
                continue
            
            if word_count >= target_min:
                logger.info(f"Generated {word_count} words, within acceptable range")
                break
            elif attempt < max_retries - 1:
                logger.warning(f"Word count {word_count} below target {target_min}, enhancing content for retry...")
                continue
        
        # Final optimization
        unified_result['unified_analysis'] = self._optimize_markup_density(
            unified_result['unified_analysis']
        )
        
        return unified_result
    
    def _preprocess_content_for_ai(self, primary_content: str, full_text: str, filing_type: Union[FilingType, str], attempt: int) -> str:
        """
        Preprocess content to ensure AI gets high-quality input
        FIXED: Safe filing type handling
        """
        if attempt == 0:
            content = primary_content
        else:
            content = primary_content + "\n\n[Additional Context]\n\n" + full_text[len(primary_content):len(primary_content) + 20000 * attempt]
        
        # Check token count
        prompt_tokens = 2000
        available_tokens = self.max_input_tokens - prompt_tokens - self.target_output_tokens
        
        # Smart truncate if needed
        content = self._smart_truncate_content(content, available_tokens, filing_type)
        
        # Clean up content
        content = self._clean_content_for_ai(content)
        
        logger.info(f"Preprocessed content: {self._count_tokens(content)} tokens, {len(content)} chars")
        
        return content
    
    def _clean_content_for_ai(self, content: str) -> str:
        """Clean content for better AI processing"""
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
        content = re.sub(r'Table of Contents', '', content, flags=re.IGNORECASE)
        
        return content.strip()
    
    def _validate_content_quality(self, analysis: str, filing_type: Union[FilingType, str]) -> bool:
        """
        Validate that the generated analysis has sufficient quality
        FIXED: Safe filing type handling
        """
        # Handle both FilingType enum and string
        if isinstance(filing_type, str):
            filing_type_value = filing_type
        else:
            filing_type_value = self._get_safe_filing_type_value(filing_type)
        
        # Check for minimum financial data mentions
        financial_mentions = len(re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', analysis))
        
        # Convert string values to FilingType for comparison if needed
        if filing_type_value in ['FORM_10K', '10-K']:
            if financial_mentions < 5:
                logger.warning(f"Insufficient financial data in analysis: {financial_mentions} mentions")
                return False
        elif filing_type_value in ['FORM_10Q', '10-Q']:
            if financial_mentions < 5:
                logger.warning(f"Insufficient financial data in analysis: {financial_mentions} mentions")
                return False
        
        # Check for key sections
        if filing_type_value in ['FORM_10K', '10-K']:
            required_topics = ['revenue', 'income', 'business', 'management']
            found_topics = sum(1 for topic in required_topics if topic.lower() in analysis.lower())
            if found_topics < 2:
                logger.warning("Missing key topics in 10-K analysis")
                return False
        
        # Check for substantive paragraphs
        paragraphs = [p for p in analysis.split('\n\n') if len(p) > 100]
        if len(paragraphs) < 3:
            logger.warning("Insufficient substantive paragraphs")
            return False
        
        # Check for data markings
        total_markings = sum(
            len(re.findall(pattern, analysis)) 
            for pattern in DATA_SOURCE_PATTERNS.values()
        )
        if total_markings < 3:
            logger.warning(f"Insufficient data source markings: {total_markings}")
            return False
        
        return True
    
    def _contains_template_numbers(self, text: str) -> bool:
        """Check if analysis contains suspicious template numbers"""
        template_patterns = [
            r'\$5\.2B',
            r'exceeded.*by.*6%',
            r'\$4\.9B',
            r'placeholder',
            r'INSERT.*HERE',
            r'TBD',
            r'\$X\.X+B',  # Placeholder formats
            r'\d+\.X+%',  # Placeholder percentages
        ]
        
        for pattern in template_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    async def _generate_unified_analysis(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str,
        analyst_data: Optional[Dict] = None
    ) -> Dict:
        """Generate unified analysis with enhanced management focus"""
        content = primary_content  # Already preprocessed
        
        # Build filing-specific context
        filing_context = self._build_filing_context(filing, analyst_data)
        
        # FIXED: Safe filing type value access
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        # Generate unified analysis with enhanced prompts
        if filing_type_value in ['FORM_10K', '10-K']:
            prompt = self._build_10k_unified_prompt_enhanced(filing, content, filing_context)
        elif filing_type_value in ['FORM_10Q', '10-Q']:
            prompt = self._build_10q_unified_prompt_enhanced(filing, content, filing_context, analyst_data)
        elif filing_type_value in ['FORM_8K', '8-K']:
            prompt = self._build_8k_unified_prompt(filing, content, filing_context)
        elif filing_type_value in ['FORM_S1', 'S-1']:
            prompt = self._build_s1_unified_prompt_enhanced(filing, content, filing_context)
        else:
            prompt = self._build_generic_unified_prompt(filing, content, filing_context)
        
        # Log token usage
        prompt_tokens = self._count_tokens(prompt)
        logger.info(f"Prompt tokens: {prompt_tokens}")
        
        # Generate unified analysis
        unified_analysis = await self._generate_text(
            prompt, 
            max_tokens=settings.AI_UNIFIED_ANALYSIS_MAX_TOKENS
        )
        
        # Generate compelling feed summary
        feed_summary = await self._generate_feed_summary_from_unified(
            unified_analysis, 
            filing_type_value,
            filing
        )
        
        # Extract smart markup data
        markup_data = self._extract_markup_data(unified_analysis)
        
        return {
            'unified_analysis': unified_analysis,
            'feed_summary': feed_summary,
            'markup_data': markup_data
        }
    
    def _build_data_marking_instructions(self) -> str:
        """Build critical instructions for mandatory data source marking - ENHANCED"""
        return """
CRITICAL REQUIREMENT: Data Source Marking System
================================================
You are reviewing this filing with the rigor of a financial journalist.
The document's tables and explicitly stated numbers are your primary sources.
Let the document tell its story through actual data, not approximations.

EVERY factual claim, number, or data point MUST be marked with its source using these tags:

1. [DOC: location] - For information directly from THIS filing
   Examples: [DOC: Financial Statements], [DOC: MD&A p.3], [DOC: Risk Factors section]
   Examples: [DOC: Consolidated Income Statement], [DOC: Management Discussion]

2. [API: source] - For external data we provided (like analyst estimates)
   Example: [API: FMP analyst consensus]

3. [CALC: formula] - For calculations you perform
   Example: [CALC: Q3/Q2-1 = 12% growth], [CALC: $15,009M/$13,640M-1 = 10% growth]

4. [NO_DATA] - When specific data is not available
   Example: "Analyst consensus data [NO_DATA], so we cannot compare to expectations"

5. [CAUTION] - For uncertain inferences or estimates
   Example: "This suggests [CAUTION] potential margin pressure"

ENHANCED RULE - Table Priority:
When citing financial figures, prioritize data from Markdown tables.
Tables are formatted as:
| Metric | Value |
|--------|-------|
| Revenue | $15,009M |
If you see this structure, use these exact values with [DOC: Table] citations.

RULES:
- Numbers without source tags will be REJECTED
- If you mention analyst expectations, you MUST have [API: FMP] or use [NO_DATA]
- Never invent or estimate consensus figures
- Mark at least one source per major paragraph
- Markdown tables are your most reliable data source
"""
    
    def _build_10k_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """Enhanced 10-K prompt with management analysis focus and data accuracy constraints"""
        marking_instructions = self._build_data_marking_instructions()
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        # FIXED: Safe filing type access
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""You are a seasoned equity analyst writing for retail investors who want professional insights in accessible language.

{marking_instructions}

CORE MISSION: 
Create a comprehensive analysis of this annual report that helps readers understand {company_name}'s ({ticker}) year in review, future prospects, and management effectiveness.

WORD COUNT GUIDANCE:
Aim for 800-1200 words if the filing provides rich information.
Quality and accuracy always take priority over length.

CRITICAL ANALYSIS AREAS:

1. **Financial Performance & Trends**
   - Revenue growth trajectory and drivers [DOC: location]
   - Profitability trends and margin analysis
   - Cash flow generation and capital allocation
   - Key segment performance

2. **Management Discussion & Analysis (MD&A)**
   - Management's explanation of results [DOC: MD&A]
   - Forward-looking statements and guidance
   - Strategic initiatives and their progress
   - Capital allocation decisions

3. **Management Perspective**
   - How management explains performance and challenges [DOC: MD&A]
   - Key strategic priorities and confidence level in outlook
   - Notable quotes that reveal management thinking
   - Tone shifts: optimistic, cautious, or defensive
   - Accountability: ownership of results vs external attribution

4. **Risk Assessment**
   - Top 3-5 material risks from Risk Factors [DOC: Risk Factors]
   - How management is addressing these risks
   - New risks vs. prior year

5. **Strategic Direction**
   - Business model evolution
   - Competitive positioning changes
   - Investment priorities and R&D focus
   - M&A activity or strategic partnerships

KEY PRINCIPLES:
- Start with your most compelling finding from the annual results
- Use ## headers for major sections
- Use *asterisks* for key financial metrics
- Use **bold** for important strategic concepts
- Use +[positive developments] sparingly for major wins
- Use -[challenges] sparingly for significant concerns
- Include management's perspective where available
- NEVER invent numbers - cite every financial figure with [DOC: location]

CONTEXT:
Fiscal Year: {context.get('fiscal_year', 'FY2024')}
Period End: {context.get('period_end_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Now, provide a comprehensive analysis of {ticker}'s annual report with complete source attribution."""
    
    def _build_10q_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict, analyst_data: Optional[Dict] = None) -> str:
        """Enhanced 10-Q prompt with management outlook focus and data accuracy constraints"""
        marking_instructions = self._build_data_marking_instructions()
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        analyst_context = ""
        if analyst_data:
            rev_est = analyst_data.get('revenue_estimate', {})
            eps_est = analyst_data.get('eps_estimate', {})
            
            if rev_est.get('value') or eps_est.get('value'):
                analyst_context = "\nANALYST EXPECTATIONS [API: FMP]:"
                
                if rev_est.get('value'):
                    analyst_context += f"\nRevenue Consensus: ${rev_est.get('value')}B"
                    if rev_est.get('analysts'):
                        analyst_context += f" ({rev_est.get('analysts')} analysts)"
                        
                if eps_est.get('value'):
                    analyst_context += f"\nEPS Consensus: ${eps_est.get('value')}"
                    if eps_est.get('analysts'):
                        analyst_context += f" ({eps_est.get('analysts')} analysts)"
                
                analyst_context += "\nCompare these expectations with actual results and mark all comparisons with [API: FMP]\n"
        else:
            analyst_context = "\nNOTE: No analyst consensus data available. Use [NO_DATA] if you need to mention expectations.\n"
        
        return f"""You are a professional equity analyst writing for retail investors seeking clear quarterly insights.

{marking_instructions}

CORE MISSION:
Write an analysis of {company_name}'s ({ticker}) quarterly results that answers: What happened? Why does it matter? What's management saying about the future?

WORD COUNT GUIDANCE:
Target 600-1000 words based on available information.
Never pad with speculation - accuracy matters more than length.

CRITICAL ANALYSIS AREAS:

1. **Quarterly Performance**
   - Revenue and earnings vs. prior year quarter [DOC: Financial Statements]
   - Sequential quarter trends
   - Beat/miss vs. expectations (if available)
   - Key operating metrics

2. **Management Commentary**
   - How management explains performance and challenges [DOC: MD&A]
   - Key strategic priorities and confidence level in outlook
   - Notable quotes that reveal management thinking
   - Tone shifts: optimistic, cautious, or defensive
   - Accountability: ownership of results vs external attribution

3. **Operational Highlights**
   - Business segment performance
   - Geographic or product mix changes
   - Margin trends and drivers
   - Working capital and cash flow dynamics

4. **Forward-Looking Indicators**
   - Management guidance (if provided) [DOC: Outlook section]
   - Investment areas and priorities
   - Anticipated headwinds or tailwinds
   - Strategic initiatives progress

5. **Key Takeaways**
   - What this quarter reveals about business health
   - Management execution quality
   - Implications for future quarters

ANALYSIS APPROACH:
- Open with the quarter's defining moment or metric
- Present actual results clearly with source marks
- Include management's perspective throughout
- Connect the numbers to business realities
- Close with concrete takeaways for investors
- NEVER fabricate analyst comparisons - use [NO_DATA] if needed

CONTEXT:
Quarter: {context.get('fiscal_quarter', 'Q3 2024')}
Current Date: {datetime.now().strftime('%B %d, %Y')}
{analyst_context}

FILING CONTENT:
{content}

Analyze this quarter's performance with complete source attribution and management perspective."""
    
    def _build_s1_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """Enhanced S-1 prompt with better investment thesis focus and data accuracy"""
        marking_instructions = self._build_data_marking_instructions()
        company_name = filing.company.name if filing.company else "the company"
        ticker = self._get_safe_ticker(filing)
        
        company_identifier = company_name
        if ticker and ticker not in ["UNKNOWN", "PRE-IPO"] and not ticker.startswith("CIK"):
            company_identifier = f"{company_name} ({ticker})"
        
        return f"""You are an IPO analyst evaluating {company_identifier}'s public offering for potential investors.

{marking_instructions}

CORE MISSION:
Create an analysis that helps investors understand the investment opportunity, risks, and company's competitive position.

WORD COUNT GUIDANCE:
Target 600-1000 words based on disclosure completeness.
For SPACs or early-stage companies with limited operating history, 600 words focused on structure and risks is appropriate.

CRITICAL ANALYSIS AREAS:

1. **Investment Thesis**
   - What problem does the company solve? [DOC: Business section]
   - Market opportunity size and growth potential
   - Competitive advantages and moat
   - Why go public now?

2. **Business Model & Economics**
   - Revenue model and pricing [DOC: Business section]
   - Unit economics and margins (if disclosed)
   - Customer concentration and retention
   - Path to profitability timeline

3. **Management & Governance**
   - Management team experience and track record [DOC: Management section]
   - Board composition and independence
   - Insider ownership and alignment
   - Corporate governance structure

4. **Financial Profile**
   - Historical revenue growth [DOC: Financial Statements]
   - Cash burn rate and runway
   - Use of IPO proceeds [DOC: Use of Proceeds]
   - Valuation considerations

5. **Risk Assessment**
   - Top 3-5 material risks [DOC: Risk Factors]
   - Competitive threats
   - Regulatory or legal concerns
   - Execution risks

6. **IPO Details**
   - Offering size and structure [DOC: The Offering]
   - Underwriters and their reputation
   - Lock-up provisions
   - Expected trading dynamics

For SPACs/Early-Stage:
- Focus on sponsor track record and incentives
- Target acquisition criteria
- Trust structure and investor protections

REMEMBER: Quality analysis over speculation! NEVER invent financial metrics.

CONTEXT:
Filing Date: {context.get('filing_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Evaluate this IPO opportunity with complete source citations and balanced perspective."""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """8-K prompt with enhanced data accuracy constraints"""
        marking_instructions = self._build_data_marking_instructions()
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        has_exhibit = "EXHIBIT 99 CONTENT" in content or "Exhibit 99:" in content
        event_type = context.get('event_type', 'Material Event')
        item_type = context.get('item_type', '')
        
        type_specific_guidance = ""
        
        if item_type and item_type.startswith('2.02'):
            type_specific_guidance = """
EARNINGS-SPECIFIC FOCUS:
- Extract and highlight: Revenue, EPS, key segment performance
- Identify the primary drivers of performance
- Note any guidance updates or management outlook changes
- Cite all numbers with [DOC: Item 2.02] or [DOC: Exhibit 99]"""
        elif item_type and item_type.startswith('1.01'):
            type_specific_guidance = """
AGREEMENT-SPECIFIC FOCUS:
- Summarize the key terms: parties, duration, financial terms
- Explain the strategic rationale and expected benefits
- Assess the potential financial and operational impact
- Cite all details with [DOC: Item 1.01]"""
        elif item_type and item_type.startswith('5.02'):
            type_specific_guidance = """
LEADERSHIP-SPECIFIC FOCUS:
- Clearly state who is leaving/joining and their roles
- Note effective dates and transition arrangements
- Assess potential impact on strategy or operations
- Cite all information with [DOC: Item 5.02]"""
        
        # FIXED: Safe filing type access
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""You are a financial journalist analyzing a material event for {company_name} ({ticker}).

{marking_instructions}

CORE MISSION:
Explain this event's significance and likely impact on the company and its investors.

WORD COUNT GUIDANCE:
Target 400-800 words depending on the event's complexity.

CONTENT CONTEXT:
This 8-K filing reports: {event_type}
{f"The filing includes Exhibit 99 with detailed supplementary information" if has_exhibit else ""}

{type_specific_guidance}

ANALYSIS FRAMEWORK:
- Lead with the most newsworthy aspect
- Provide essential context and details
- Mark every factual claim with its source
- Explain the business/financial impact
- Close with what to watch for next
- NEVER speculate on numbers - cite everything

CONTEXT:
Event Date: {context.get('filing_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Analyze this event with complete source attribution."""
    
    def _build_generic_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Generic prompt for other filing types with data accuracy constraints"""
        marking_instructions = self._build_data_marking_instructions()
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        # FIXED: Safe filing type access
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""You are a financial analyst examining this {filing_type_value} filing for {company_name} ({ticker}).

{marking_instructions}

WORD COUNT GUIDANCE:
Target 500-800 words, adjusting to the filing's information density.

Write an analysis that:
1. Identifies the key disclosures and their significance
2. Explains the implications for investors
3. Uses specific data from the filing with [DOC: location] citations
4. Maintains professional clarity throughout
5. NEVER invents or approximates numbers

Focus on what's material and actionable for investors.

FILING CONTENT:
{content}"""
    
    def _build_filing_context(self, filing: Filing, analyst_data: Optional[Dict] = None) -> Dict:
        """Build context dictionary for prompt generation"""
        context = {
            'fiscal_year': filing.fiscal_year,
            'fiscal_quarter': filing.fiscal_quarter,
            'period_end_date': filing.period_end_date.strftime('%B %d, %Y') if filing.period_end_date else None,
            'filing_date': filing.filing_date.strftime('%B %d, %Y'),
        }
        
        if analyst_data:
            context['analyst_data'] = analyst_data
        
        if filing.filing_type == FilingType.FORM_8K:
            context['event_type'] = self._identify_8k_event_type(filing.primary_content if hasattr(filing, 'primary_content') else '')
            context['item_type'] = filing.item_type if hasattr(filing, 'item_type') else ''
            
        return context
    
    async def _generate_feed_summary_from_unified(self, unified_analysis: str, filing_type: str, filing: Filing) -> str:
        """Generate a compelling feed summary from unified analysis"""
        key_numbers = re.findall(r'\*([^*]+)\*', unified_analysis)[:5]
        key_concepts = re.findall(r'\*\*([^*]+)\*\*', unified_analysis)[:3]
        positive_points = re.findall(r'\+\[([^\]]+)\]', unified_analysis)[:2]
        negative_points = re.findall(r'-\[([^\]]+)\]', unified_analysis)[:2]
        
        narrative_elements = {
            'numbers': key_numbers,
            'concepts': key_concepts,
            'positive': positive_points,
            'negative': negative_points,
            'has_contrast': len(positive_points) > 0 and len(negative_points) > 0,
            'has_surprise': any(word in unified_analysis.lower() for word in ['exceeded', 'missed', 'surprised', 'unexpected']),
            'has_guidance': 'guidance' in unified_analysis.lower(),
            'has_transformation': any(word in unified_analysis.lower() for word in ['transform', 'pivot', 'restructur', 'strategic shift'])
        }
        
        # Build filing type specific prompts
        if filing_type in ["FORM_10K", "10-K"]:
            prompt = self._build_10k_summary_prompt(filing, narrative_elements, unified_analysis)
        elif filing_type in ["FORM_10Q", "10-Q"]:
            prompt = self._build_10q_summary_prompt(filing, narrative_elements, unified_analysis)
        elif filing_type in ["FORM_8K", "8-K"]:
            prompt = self._build_8k_summary_prompt(filing, narrative_elements, unified_analysis)
        elif filing_type in ["FORM_S1", "S-1"]:
            prompt = self._build_s1_summary_prompt(filing, narrative_elements, unified_analysis)
        else:
            prompt = self._build_generic_summary_prompt(filing, narrative_elements, unified_analysis)

        summary = await self._generate_text(prompt, max_tokens=100)
        
        ticker = self._get_safe_ticker(filing)
        
        if ticker not in summary:
            summary = f"{ticker}: {summary}"
        
        if len(summary) > 300:
            sentences = summary.split('. ')
            truncated = sentences[0] + '. ' + sentences[1] + '.'
            if len(truncated) <= 300:
                summary = truncated
            else:
                summary = sentences[0] + '...'
        
        # Clean up data source markers
        summary = re.sub(r'\[DOC:[^\]]+\]', '', summary)
        summary = re.sub(r'\[API:[^\]]+\]', '', summary)
        summary = re.sub(r'\[CALC:[^\]]+\]', '', summary)
        summary = re.sub(r'\s+', ' ', summary).strip()
        
        return summary
    
    def _build_10k_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build compelling summary prompt for 10-K filings"""
        ticker = self._get_safe_ticker(filing)
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s annual report.

Key elements to potentially include:
- Numbers: {', '.join(elements['numbers'][:2]) if elements['numbers'] else 'No standout numbers'}
- Themes: {', '.join(elements['concepts'][:2]) if elements['concepts'] else 'Standard year'}
- Tone: {'Mixed signals' if elements['has_contrast'] else 'Consistent direction'}

Requirements:
1. Start with ticker: "{ticker}:"
2. Lead with the most newsworthy aspect
3. Create tension or interest if there's contrast
4. Use specific numbers where impactful
5. Make investors want to read more

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_10q_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build compelling summary prompt for 10-Q filings"""
        ticker = self._get_safe_ticker(filing)
        has_beat_miss = elements['has_surprise']
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s quarterly results.

Key elements:
- Numbers: {', '.join(elements['numbers'][:3]) if elements['numbers'] else 'Core metrics'}
- Beat/Miss: {'Yes - highlight this!' if has_beat_miss else 'In-line results'}
- Guidance: {'Updated' if elements['has_guidance'] else 'Not mentioned'}

Requirements:
1. Start with ticker: "{ticker}:"
2. Lead with beat/miss if significant, otherwise biggest change
3. Include specific % or $ that tells the story
4. Add context about what drove results

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_8k_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build compelling summary prompt for 8-K filings"""
        ticker = self._get_safe_ticker(filing)
        
        event_keywords = {
            'executive': 'Leadership Change',
            'acquisition': 'M&A Activity',
            'earnings': 'Earnings Update',
            'agreement': 'Material Agreement',
            'dividend': 'Capital Return',
            'guidance': 'Guidance Update'
        }
        
        event_type = 'Material Event'
        for keyword, event_name in event_keywords.items():
            if keyword in analysis_excerpt.lower():
                event_type = event_name
                break
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s {event_type}.

Requirements:
1. Start with ticker: "{ticker}:"
2. State what happened with specifics
3. Immediately explain why it matters
4. Use active voice and strong verbs

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_s1_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build compelling summary prompt for S-1 filings"""
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else ticker
        
        identifier = company_name if ticker in ["UNKNOWN", "PRE-IPO"] or ticker.startswith("CIK") else ticker
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {identifier}'s IPO filing.

Requirements:
1. Start with identifier: "{identifier}:"
2. Capture what makes this IPO unique or risky
3. Include valuation context or growth rate
4. Highlight the investment tension

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_generic_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build generic compelling summary prompt"""
        ticker = self._get_safe_ticker(filing)
        
        # FIXED: Safe filing type access
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s {filing_type_value} filing.

Requirements:
1. Start with ticker: "{ticker}:"
2. Identify the most significant disclosure
3. Explain immediate impact
4. Use specific data points

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _extract_markup_data(self, text: str) -> Dict:
        """Extract smart markup metadata for frontend rendering"""
        markup_data = {
            'numbers': [],
            'concepts': [],
            'positive': [],
            'negative': [],
            'sections': [],
            'sources': []
        }
        
        # FIXED: Corrected regex pattern - was missing closing quote
        sections = re.findall(r'^##\s+(.+)', text, re.MULTILINE)
        markup_data['sections'] = sections
        
        numbers = re.findall(r'\*([^*]+)\*', text)
        markup_data['numbers'] = numbers[:10]
        
        concepts = re.findall(r'\*\*([^*]+)\*\*', text)
        markup_data['concepts'] = concepts[:8]
        
        positive = re.findall(r'\+\[([^\]]+)\]', text)
        markup_data['positive'] = positive[:5]
        
        negative = re.findall(r'-\[([^\]]+)\]', text)
        markup_data['negative'] = negative[:5]
        
        for pattern_name, pattern in DATA_SOURCE_PATTERNS.items():
            matches = re.findall(pattern, text)
            for match in matches[:5]:
                markup_data['sources'].append({
                    'type': pattern_name,
                    'reference': match
                })
        
        return markup_data
    
    def _optimize_markup_density(self, text: str) -> str:
        """Monitor markup density without forcing changes"""
        total_length = len(text)
        
        markup_patterns = [
            r'\*[^*]+\*',
            r'\*\*[^*]+\*\*',
            r'\+\[[^\]]+\]',
            r'-\[[^\]]+\]'
        ]
        
        markup_patterns.extend(DATA_SOURCE_PATTERNS.values())
        
        markup_chars = 0
        for pattern in markup_patterns:
            matches = re.findall(pattern, text)
            markup_chars += sum(len(match) for match in matches)
        
        density = markup_chars / total_length if total_length > 0 else 0
        
        logger.info(f"Markup density: {density:.2%}")
        
        return text
    
    async def _extract_supplementary_fields(self, filing: Filing, unified_result: Dict, primary_content: str, full_text: str):
        """Extract supplementary fields from unified analysis - Streamlined version"""
        unified_text = unified_result['unified_analysis']
        
        ticker = self._get_safe_ticker(filing)
        
        # Extract enhanced tags from markup data and content
        filing.key_tags = self._generate_enhanced_tags(unified_result['markup_data'], unified_text, filing.filing_type, ticker)
        
        # For backward compatibility - set these fields to None/empty
        filing.management_tone = None
        filing.tone_explanation = None
        filing.key_questions = []
        filing.financial_highlights = None
        filing.ai_summary = None  # No longer needed, using unified_analysis
        
        # Extract event-specific fields for 8-K
        if filing.filing_type == FilingType.FORM_8K:
            filing.event_type = self._identify_8k_event_type(primary_content)
            filing.item_type = self._extract_8k_item_type(primary_content)
        
        # Format expectations comparison for 10-Q if analyst data exists
        if filing.filing_type == FilingType.FORM_10Q and unified_result.get('analyst_data'):
            filing.expectations_comparison = self._format_expectations_comparison(unified_result['analyst_data'])
    
    def _generate_enhanced_tags(self, markup_data: Dict, unified_text: str, filing_type: Union[FilingType, str], ticker: str) -> List[str]:
        """
        Generate enhanced tags with better industry and financial relevance
        FIXED: Safe filing type handling
        """
        tags = []
        text_lower = unified_text.lower()
        
        # Industry-specific tags based on content
        industry_keywords = {
            'Technology': ['software', 'cloud', 'saas', 'platform', 'digital', 'ai', 'machine learning'],
            'Healthcare': ['drug', 'clinical', 'fda', 'patient', 'therapeutic', 'biotech', 'pharmaceutical'],
            'Financial': ['banking', 'loan', 'deposit', 'interest rate', 'credit', 'insurance'],
            'Retail': ['store', 'e-commerce', 'consumer', 'brand', 'inventory', 'same-store'],
            'Energy': ['oil', 'gas', 'renewable', 'drilling', 'exploration', 'barrel'],
            'Manufacturing': ['production', 'supply chain', 'factory', 'capacity', 'automotive']
        }
        
        for industry, keywords in industry_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                tags.append(industry)
                break
        
        # Financial performance tags based on markup
        if markup_data['positive']:
            positive_text = ' '.join(markup_data['positive']).lower()
            if any(term in positive_text for term in ['beat', 'exceed', 'record', 'growth']):
                tags.append('Outperformance')
            if 'guidance' in positive_text and 'raised' in positive_text:
                tags.append('Guidance Raised')
        
        if markup_data['negative']:
            negative_text = ' '.join(markup_data['negative']).lower()
            if any(term in negative_text for term in ['miss', 'below', 'decline', 'loss']):
                tags.append('Underperformance')
            if 'guidance' in negative_text and any(term in negative_text for term in ['lowered', 'reduced']):
                tags.append('Guidance Lowered')
        
        # Key metric tags
        if 'margin' in text_lower:
            if 'expansion' in text_lower or 'improve' in text_lower:
                tags.append('Margin Expansion')
            elif 'pressure' in text_lower or 'compress' in text_lower:
                tags.append('Margin Pressure')
        
        # Management-related tags
        if any(term in text_lower for term in ['ceo', 'cfo', 'executive', 'management change']):
            if any(term in text_lower for term in ['new', 'appoint', 'hire']):
                tags.append('Management Change')
        
        # Corporate action tags
        if 'dividend' in text_lower:
            tags.append('Dividend')
        if any(term in text_lower for term in ['buyback', 'repurchase', 'share repurchase']):
            tags.append('Share Buyback')
        if any(term in text_lower for term in ['acquisition', 'merger', 'm&a', 'acquire']):
            tags.append('M&A Activity')
        if 'restructuring' in text_lower:
            tags.append('Restructuring')
        
        # Filing type tag - FIXED: Safe filing type handling
        filing_type_tags = {
            'FORM_10K': 'Annual Report',
            '10-K': 'Annual Report',
            'FORM_10Q': 'Quarterly Results',
            '10-Q': 'Quarterly Results',
            'FORM_8K': 'Material Event',
            '8-K': 'Material Event',
            'FORM_S1': 'IPO Filing',
            'S-1': 'IPO Filing'
        }
        
        # Handle both enum and string types
        if isinstance(filing_type, str):
            filing_type_key = filing_type
        else:
            filing_type_key = self._get_safe_filing_type_value(filing_type)
        
        if filing_type_key in filing_type_tags:
            tags.append(filing_type_tags[filing_type_key])
        
        # Ticker-specific tag if it's a well-known company
        if ticker and len(ticker) <= 5 and not ticker.startswith('CIK'):
            # Could add logic here to tag as "Large Cap", "Small Cap", etc. based on market cap
            pass
        
        # Remove duplicates and limit to 7 tags
        tags = list(dict.fromkeys(tags))[:7]
        
        return tags
    
    def _format_expectations_comparison(self, analyst_data: Dict) -> str:
        """Format expectations comparison for storage"""
        revenue_est = analyst_data.get('revenue_estimate', {})
        eps_est = analyst_data.get('eps_estimate', {})
        
        comparison = f"Analyst Expectations: "
        if revenue_est.get('value'):
            comparison += f"Revenue estimate ${revenue_est['value']}B ({revenue_est.get('analysts', 0)} analysts). "
        if eps_est.get('value'):
            comparison += f"EPS estimate ${eps_est['value']} ({eps_est.get('analysts', 0)} analysts)."
            
        return comparison
    
    def _identify_8k_event_type(self, content: str) -> str:
        """Identify the type of 8-K event from content"""
        content_lower = content.lower()
        
        if 'item 2.02' in content_lower:
            return "Earnings Release"
        elif 'item 1.01' in content_lower:
            return "Material Agreement"
        elif 'item 5.02' in content_lower:
            return "Executive Change"
        elif 'item 7.01' in content_lower:
            return "Regulation FD Disclosure"
        elif 'item 8.01' in content_lower:
            return "Other Material Event"
        elif 'results of operations' in content_lower or 'financial condition' in content_lower:
            return "Earnings Release"
        elif 'entry into' in content_lower and 'agreement' in content_lower:
            return "Material Agreement"
        elif ('departure' in content_lower or 'appointment' in content_lower) and 'officer' in content_lower:
            return "Executive Change"
        elif 'merger' in content_lower or 'acquisition' in content_lower:
            return "M&A Activity"
        elif 'dividend' in content_lower:
            return "Dividend Announcement"
        else:
            return "Corporate Event"
    
    def _extract_8k_item_type(self, content: str) -> Optional[str]:
        """Extract Item number from 8-K content"""
        item_pattern = r'Item\s+(\d+\.\d+)'
        match = re.search(item_pattern, content, re.IGNORECASE)
        return match.group(1) if match else None
    
    async def _generate_text(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate text using OpenAI"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst with expertise in SEC filings analysis. Write in clear, professional English suitable for sophisticated retail investors. Always cite your sources with proper data marking tags."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=self.temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            return ""


# Initialize singleton
ai_processor = AIProcessor()