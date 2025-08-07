# app/services/ai_processor.py
"""
AI Processor Service - Enhanced Version with Compelling Feed Summaries
Implements intelligent guidance approach with unified analysis
CRITICAL: Implements mandatory data source marking to prevent hallucination
ENHANCED: Smart content preprocessing and token management
ENHANCED: Filing type awareness for better prompts
UPDATED: Integrated FMP for analyst expectations
FIXED: Use period_end_date instead of period_date for analyst estimates matching
ENHANCED: Better 8-K processing with Exhibit 99 awareness
ENHANCED: Compelling feed summaries with data integrity
FIXED: Changed ProcessingStatus.AI_PROCESSING to ProcessingStatus.ANALYZING
FIXED: Handle None ticker values for SPAC/IPO companies
OPTIMIZED: Flexible word count requirements prioritizing accuracy over length
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
from pathlib import Path
import asyncio
import tiktoken

from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.filing import Filing, ProcessingStatus, ManagementTone, FilingType
from app.core.config import settings
from app.services.text_extractor import text_extractor
from app.services.fmp_service import fmp_service
from app.core.cache import cache

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# CRITICAL: Data source marking patterns
DATA_SOURCE_PATTERNS = {
    'document': r'\[DOC:\s*([^\]]+)\]',  # [DOC: page/location]
    'api': r'\[API:\s*([^\]]+)\]',       # [API: source]
    'calc': r'\[CALC:\s*([^\]]+)\]',     # [CALC: formula]
    'no_data': r'\[NO_DATA\]',           # [NO_DATA]
    'caution': r'\[CAUTION\]'            # [CAUTION]
}

class AIProcessor:
    """
    Process filings using OpenAI to generate unified analysis with intelligent guidance
    Enhanced with mandatory data source marking system and compelling summaries
    """
    
    def __init__(self):
        self.model = settings.AI_MODEL
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        
        # Initialize tokenizer for accurate token counting
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except:
            # Fallback to cl100k_base encoding
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Token limits with safety margin
        self.max_input_tokens = 100000  # Conservative limit to avoid errors
        self.target_output_tokens = 3000  # For unified analysis
    
    def _get_safe_ticker(self, filing: Filing) -> str:
        """
        Get ticker safely, returning a default value if None
        """
        if filing.ticker:
            return filing.ticker
        elif filing.company and filing.company.ticker:
            return filing.company.ticker
        else:
            # For S-1 filings without ticker, use company name or CIK
            if filing.filing_type == FilingType.FORM_S1:
                if filing.company and filing.company.name:
                    # Take first word of company name or use "PRE-IPO"
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
            # Fallback estimation
            return len(text) // 4
    
    def _validate_data_marking(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validate that AI output contains proper data source markings
        Returns: (is_valid, list_of_issues)
        """
        issues = []
        
        # Extract all numbers and claims
        numbers = re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', text)
        
        # Check if numbers have nearby citations
        for number in numbers[:10]:  # Check first 10 numbers
            # Find position of this number
            pos = text.find(number)
            if pos == -1:
                continue
                
            # Check for citation within 100 chars
            nearby_text = text[max(0, pos-50):pos+50]
            has_citation = any(
                re.search(pattern, nearby_text) 
                for pattern in DATA_SOURCE_PATTERNS.values()
            )
            
            if not has_citation:
                issues.append(f"Unmarked number: {number}")
        
        # Check for forbidden phrases when NO_DATA should be used
        if '[NO_DATA]' not in text:
            forbidden_without_data = [
                'analyst consensus', 'analyst expectations',
                'beat expectations', 'missed estimates',
                'exceeded analyst', 'below analyst'
            ]
            for phrase in forbidden_without_data:
                if phrase.lower() in text.lower():
                    # Check if we actually have analyst data
                    if not re.search(r'\[API:\s*FMP\]', text):
                        issues.append(f"Used '{phrase}' without analyst data or [NO_DATA] marker")
        
        # Check minimum marking density
        total_markings = sum(
            len(re.findall(pattern, text)) 
            for pattern in DATA_SOURCE_PATTERNS.values()
        )
        
        if len(text) > 1000 and total_markings < 5:
            issues.append("Insufficient data source markings for content length")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def _smart_truncate_content(self, content: str, max_tokens: int, filing_type: str) -> str:
        """
        Intelligently truncate content while preserving key sections
        """
        current_tokens = self._count_tokens(content)
        
        if current_tokens <= max_tokens:
            return content
        
        logger.info(f"Content needs truncation: {current_tokens} tokens > {max_tokens} limit")
        
        # Split content into sections
        sections = content.split('\n\n')
        
        # Priority keywords for different filing types
        priority_keywords = {
            'FORM_10K': ['management discussion', 'financial statements', 'risk factors', 'business'],
            'FORM_10Q': ['financial statements', 'management discussion', 'quarter', 'three months'],
            'FORM_8K': ['item', 'event', 'agreement', 'announcement', 'exhibit 99'],
            'FORM_S1': ['summary', 'risk factors', 'use of proceeds', 'business']
        }
        
        # Score each section
        scored_sections = []
        filing_keywords = priority_keywords.get(filing_type.value, [])
        
        for section in sections:
            score = 0
            section_lower = section.lower()
            
            # Score based on keywords
            for keyword in filing_keywords:
                if keyword in section_lower:
                    score += 10
            
            # Score based on financial data
            score += len(re.findall(r'\$[\d,]+', section)) * 2
            score += len(re.findall(r'\d+\.?\d*%', section)) * 2
            
            # Score based on section markers
            if re.search(r'^={3,}|^Item\s+\d+|^Part\s+[IVX]+', section):
                score += 5
            
            # Special boost for Exhibit 99 content in 8-K
            if filing_type == FilingType.FORM_8K and 'exhibit 99' in section_lower:
                score += 20
            
            scored_sections.append((score, section))
        
        # Sort by score (highest first)
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        
        # Build truncated content
        truncated_parts = []
        total_tokens = 0
        
        for score, section in scored_sections:
            section_tokens = self._count_tokens(section)
            if total_tokens + section_tokens <= max_tokens:
                truncated_parts.append(section)
                total_tokens += section_tokens
            elif total_tokens < max_tokens * 0.9:  # Try to use at least 90% of limit
                # Partially include this section
                remaining_tokens = max_tokens - total_tokens
                partial_section = section[:remaining_tokens * 4]  # Approximate
                truncated_parts.append(partial_section + "\n[Section truncated...]")
                break
        
        result = '\n\n'.join(truncated_parts)
        logger.info(f"Truncated content from {current_tokens} to {self._count_tokens(result)} tokens")
        
        return result
        
    async def process_filing(self, db: Session, filing: Filing) -> bool:
        """
        Process a filing using unified AI analysis with mandatory data marking
        
        Args:
            db: Database session
            filing: Filing to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update status - FIXED: Use ANALYZING instead of AI_PROCESSING
            filing.status = ProcessingStatus.ANALYZING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            # FIXED: Get ticker safely
            ticker = self._get_safe_ticker(filing)
            company_name = filing.company.name if filing.company else "Unknown Company"
            
            logger.info(f"Starting enhanced AI processing for {ticker} {filing.filing_type.value}")
            
            # Get filing directory
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            
            # Extract text with enhanced extractor
            sections = text_extractor.extract_from_filing(filing_dir)
            
            if 'error' in sections:
                raise Exception(f"Text extraction failed: {sections['error']}")
            
            # Get the filing type from extraction
            extracted_filing_type = sections.get('filing_type', 'UNKNOWN')
            logger.info(f"Extracted filing type: {extracted_filing_type}")
            
            primary_content = sections.get('primary_content', '')
            full_text = sections.get('full_text', '')
            
            # For 8-K, check if Exhibit 99 content was extracted
            if filing.filing_type == FilingType.FORM_8K and 'exhibit_99_content' in sections:
                logger.info(f"8-K includes Exhibit 99 content: {len(sections['exhibit_99_content'])} chars")
            
            if not primary_content or len(primary_content) < 100:
                raise Exception("Insufficient text content extracted")
            
            # Log content quality
            logger.info(f"Extracted content - Primary: {len(primary_content)} chars, Full: {len(full_text)} chars")
            
            # Get analyst expectations for 10-Q if enabled using FMP
            analyst_data = None
            if filing.filing_type == FilingType.FORM_10Q and settings.ENABLE_EXPECTATIONS_COMPARISON and settings.FMP_ENABLE:
                # Only fetch if we have a valid ticker
                if ticker and ticker not in ["UNKNOWN", "PRE-IPO"] and not ticker.startswith("CIK"):
                    logger.info(f"[AI Processor] Fetching analyst expectations from FMP for {ticker}")
                    
                    # FIXED: Use period_end_date instead of period_date
                    target_date = None
                    if filing.period_end_date:
                        target_date = filing.period_end_date.strftime('%Y-%m-%d')
                        logger.info(f"[AI Processor] Using period end date {target_date} to fetch expectations")
                    elif filing.filing_date:
                        # Fallback: use filing_date
                        target_date = filing.filing_date.strftime('%Y-%m-%d')
                        logger.info(f"[AI Processor] Using filing date {target_date} to fetch expectations (fallback)")
                    
                    # FMP service is now synchronous
                    analyst_data = fmp_service.get_analyst_estimates(
                        ticker,
                        target_date=target_date
                    )
                    
                    if analyst_data:
                        logger.info(f"[AI Processor] Retrieved analyst expectations from FMP for {ticker}")
                        logger.info(f"[AI Processor] Expectations for period: {analyst_data.get('period')}")
                    else:
                        logger.info(f"[AI Processor] No analyst expectations available from FMP for {ticker}")
                else:
                    logger.info(f"[AI Processor] Skipping analyst expectations - no valid ticker available")
            
            # Generate unified analysis with intelligent retry and validation
            unified_result = await self._generate_unified_analysis_with_retry(
                filing, primary_content, full_text, analyst_data
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.analysis_version = "v5"  # Enhanced version with data marking
            
            if analyst_data:
                filing.analyst_expectations = analyst_data
            
            # Extract supplementary fields from unified analysis
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
    
    async def _generate_unified_analysis_with_retry(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str,
        analyst_data: Optional[Dict] = None
    ) -> Dict:
        """
        Generate unified analysis with intelligent retry logic and content optimization
        ENHANCED: With mandatory data source validation
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            # Preprocess content to ensure quality and token limits
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
                    # Add validation feedback to next attempt
                    continue
                else:
                    # Last attempt - log but accept
                    logger.error(f"Data marking validation failed after {max_retries} attempts: {validation_issues}")
            
            # Validate word count with flexibility - OPTIMIZED: More flexible minimums
            word_count = len(unified_result['unified_analysis'].split())
            
            # OPTIMIZED: Adjusted minimums based on filing type
            if filing.filing_type == FilingType.FORM_10K:
                target_min = 600  # Was ~900
            elif filing.filing_type == FilingType.FORM_10Q:
                target_min = 600  # Was ~720
            elif filing.filing_type == FilingType.FORM_8K:
                target_min = 400  # Was ~540
            elif filing.filing_type == FilingType.FORM_S1:
                target_min = 600  # Was ~720
            else:
                target_min = 500  # Generic minimum
            
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
    
    def _preprocess_content_for_ai(self, primary_content: str, full_text: str, filing_type: FilingType, attempt: int) -> str:
        """
        Preprocess content to ensure AI gets high-quality input within token limits
        """
        # Start with primary content
        if attempt == 0:
            content = primary_content
        else:
            # Use more content on retries
            content = primary_content + "\n\n[Additional Context]\n\n" + full_text[len(primary_content):len(primary_content) + 20000 * attempt]
        
        # Check token count
        prompt_tokens = 2000  # Estimate for prompt
        available_tokens = self.max_input_tokens - prompt_tokens - self.target_output_tokens
        
        # Smart truncate if needed
        content = self._smart_truncate_content(content, available_tokens, filing_type.value)
        
        # Clean up content
        content = self._clean_content_for_ai(content)
        
        # Log preprocessing results
        logger.info(f"Preprocessed content: {self._count_tokens(content)} tokens, {len(content)} chars")
        
        return content
    
    def _clean_content_for_ai(self, content: str) -> str:
        """
        Clean content for better AI processing
        """
        # Remove excessive legal boilerplate
        legal_patterns = [
            r'PURSUANT TO THE REQUIREMENTS.*?(?=\n\n|\Z)',
            r'The information.*?incorporated by reference.*?(?=\n\n|\Z)',
            r'SIGNATURES?\s*\n.*?\Z',
        ]
        
        for pattern in legal_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove excessive whitespace
        content = re.sub(r'\n{4,}', '\n\n\n', content)
        content = re.sub(r' {3,}', ' ', content)
        
        # Remove page numbers and headers
        content = re.sub(r'Page \d+ of \d+', '', content)
        content = re.sub(r'Table of Contents', '', content, flags=re.IGNORECASE)
        
        return content.strip()
    
    def _validate_content_quality(self, analysis: str, filing_type: FilingType) -> bool:
        """
        Validate that the generated analysis has sufficient quality
        ENHANCED: Also checks for proper data marking
        """
        # Check for minimum financial data mentions
        financial_mentions = len(re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', analysis))
        
        if filing_type in [FilingType.FORM_10K, FilingType.FORM_10Q]:
            if financial_mentions < 5:
                logger.warning(f"Insufficient financial data in analysis: {financial_mentions} mentions")
                return False
        
        # Check for key sections
        if filing_type == FilingType.FORM_10K:
            required_topics = ['revenue', 'income', 'business']
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
        """
        Generate unified analysis with intelligent guidance approach
        ENHANCED: With mandatory data source marking
        """
        # Use the preprocessed content
        content = primary_content  # Already preprocessed
        
        # Build filing-specific context
        filing_context = self._build_filing_context(filing, analyst_data)
        
        # Generate unified analysis with reformed prompt
        if filing.filing_type == FilingType.FORM_10K:
            prompt = self._build_10k_unified_prompt(filing, content, filing_context)
        elif filing.filing_type == FilingType.FORM_10Q:
            prompt = self._build_10q_unified_prompt(filing, content, filing_context, analyst_data)
        elif filing.filing_type == FilingType.FORM_8K:
            prompt = self._build_8k_unified_prompt(filing, content, filing_context)
        elif filing.filing_type == FilingType.FORM_S1:
            prompt = self._build_s1_unified_prompt(filing, content, filing_context)
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
        
        # Generate compelling feed summary from unified analysis
        feed_summary = await self._generate_feed_summary_from_unified(
            unified_analysis, 
            filing.filing_type.value,
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
        """
        Build critical instructions for mandatory data source marking
        OPTIMIZED: Added clarity about when exact data is not available
        """
        return """
CRITICAL REQUIREMENT: Data Source Marking System
================================================
EVERY factual claim, number, or data point MUST be marked with its source using these tags:

1. [DOC: location] - For information directly from THIS filing
   Examples: [DOC: Financial Statements], [DOC: MD&A p.3], [DOC: Risk Factors section]

2. [API: source] - For external data we provided (like analyst estimates)
   Example: [API: FMP analyst consensus]

3. [CALC: formula] - For calculations you perform
   Example: [CALC: Q3/Q2-1 = 12% growth]

4. [NO_DATA] - When specific data is not available
   Example: "Analyst consensus data [NO_DATA], so we cannot compare to expectations"

5. [CAUTION] - For uncertain inferences or estimates
   Example: "This suggests [CAUTION] potential margin pressure"

RULES:
- Numbers without source tags will be REJECTED
- If you mention analyst expectations, you MUST have [API: FMP] or use [NO_DATA]
- Never invent or estimate consensus figures
- Mark at least one source per paragraph
- When exact numbers are not disclosed, focus on qualitative information instead of inventing data

Example paragraph with proper marking:
"Revenue reached $4.2B [DOC: Financial Statements], representing 15% growth [CALC: YoY from income statement]. 
This exceeded analyst consensus of $4.0B [API: FMP] by 5% [CALC: (4.2-4.0)/4.0]. 
Management attributed the beat to strong Asia performance [DOC: MD&A regional breakdown]."

Alternative when data is limited:
"The company reported 'significant revenue growth' [DOC: CEO Letter] without disclosing specific figures [NO_DATA]. 
Management emphasized improving margins [DOC: MD&A] and expanding market share [DOC: Business Overview], 
though quantitative metrics were not provided in this filing."
"""
    
    def _build_10k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build reformed prompt for 10-K filings with mandatory data marking"""
        marking_instructions = self._build_data_marking_instructions()
        
        # FIXED: Get ticker and company name safely
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        # OPTIMIZED: Flexible word count guidance
        return f"""You are a seasoned equity analyst writing for retail investors who want professional insights in accessible language.

{marking_instructions}

CORE MISSION: 
Create a comprehensive analysis of this annual report that helps readers understand {company_name}'s ({ticker}) year in review and future prospects.

WORD COUNT GUIDANCE:
Aim for 800-1200 words if the filing provides rich information.
However, if key data is limited, a thorough 600-word analysis is better than padding with speculation.
Quality and accuracy always take priority over length.

CONTENT CONTEXT:
This filing contains key sections including business overview, risk factors, management discussion & analysis (MD&A), and financial statements. Focus on the most material information provided.

KEY PRINCIPLES:
1. **Data Integrity**: Every number must come from THIS filing with proper [DOC: location] marking
   - If specific revenue/earnings numbers aren't disclosed, analyze the qualitative discussion
   - Never invent numbers to fill gaps - use [NO_DATA] and focus on what IS disclosed
2. **Clear Narrative**: Tell the story of the year - what worked, what didn't, what's changing
3. **Professional Clarity**: Keep financial terms but explain their business significance
4. **Natural Structure**: Use ## headers and --- breaks to guide readers through your analysis
5. **Smart Emphasis**: 
   - Use *asterisks* for key financial metrics
   - Use **bold** for important strategic concepts
   - Use +[positive developments] sparingly for major wins
   - Use -[challenges] sparingly for significant concerns

QUALITY GUIDANCE:
- Start with your most compelling finding from the annual results
- Tell the story of the year through a structured lens
- Balance narrative flow with analytical rigor
- Compare actual results to guidance when available in the filing
- Identify 2-3 key risks or opportunities from the filing
- Make the implications clear for investors
- If data is limited, focus on strategic changes and qualitative insights

REMEMBER: Better to acknowledge missing data than to invent it!

CONTEXT:
Fiscal Year: {context.get('fiscal_year', 'FY2024')}
Period End: {context.get('period_end_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Now, tell the story of {ticker}'s year with proper source citations."""
    
    def _build_10q_unified_prompt(self, filing: Filing, content: str, context: Dict, analyst_data: Optional[Dict] = None) -> str:
        """Build reformed prompt for 10-Q filings with mandatory data marking"""
        marking_instructions = self._build_data_marking_instructions()
        
        # FIXED: Get ticker and company name safely
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
                
                analyst_context += "\nCompare these expectations with actual results and mark all comparisons properly\n"
        else:
            analyst_context = "\nNOTE: No analyst consensus data available. Use [NO_DATA] if you need to mention expectations.\n"
        
        # OPTIMIZED: Flexible word count guidance
        return f"""You are a professional equity analyst writing for retail investors seeking clear quarterly insights.

{marking_instructions}

CORE MISSION:
Write an analysis of {company_name}'s ({ticker}) quarterly results that answers: What happened? Why does it matter? What's next?

WORD COUNT GUIDANCE:
Target 600-1000 words based on available information.
If the filing has limited financial detail, a concise 600-word analysis is perfectly acceptable.
Never pad with speculation - accuracy matters more than length.

CONTENT CONTEXT:
This quarterly filing includes financial statements and management's discussion of the quarter's performance. Focus on the key drivers and changes.

KEY PRINCIPLES:
1. **Data Integrity & Comparison**: 
   - Use actual performance numbers from THIS filing with [DOC: location] marks
   - When analyst consensus is provided, compare actuals vs. expectations with proper [API: FMP] marking
   - If no analyst data exists, use [NO_DATA] instead of inventing numbers
   - If specific metrics aren't disclosed, focus on directional trends and management commentary
2. **Clear Story Arc**: Performance → Drivers → Implications → Outlook
3. **Professional Terms**: Keep Revenue, EBITDA, etc. but explain their significance
4. **Visual Structure**: Use ## for major sections and --- for transitions
5. **Smart Emphasis**: 
   - Use *asterisks* for key metrics from the filing
   - Use **bold** for important concepts and strategic points
   - Use +[positive trends] for beats or positive surprises
   - Use -[negative trends] for misses or challenges

ANALYSIS APPROACH:
- Open with the quarter's defining moment or metric (if available)
- Present the quarter's story within a clear analytical framework
- State actual results clearly with source marks, then compare with consensus when available
- Explain both what happened and why it matters through cause-effect narrative
- Connect the numbers to business realities and the bigger picture
- Note significant surprises and their implications
- Close with concrete takeaways for investors

REMEMBER: Quality analysis doesn't require inventing data!

CONTEXT:
Quarter: {context.get('fiscal_quarter', 'Q3 2024')}
Current Date: {datetime.now().strftime('%B %d, %Y')}
{analyst_context}

FILING CONTENT:
{content}

Analyze this quarter's performance with complete source attribution."""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build enhanced prompt for 8-K filings with mandatory data marking"""
        marking_instructions = self._build_data_marking_instructions()
        
        # FIXED: Get ticker and company name safely
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        # Detect if Exhibit 99 content is present
        has_exhibit = "EXHIBIT 99 CONTENT" in content or "Exhibit 99:" in content
        
        # Identify the type of 8-K based on Item numbers and content
        event_type = context.get('event_type', 'Material Event')
        item_type = context.get('item_type', '')
        
        # Build type-specific guidance based on Item type
        type_specific_guidance = ""
        
        if item_type and item_type.startswith('2.02'):  # Earnings Release
            type_specific_guidance = """
EARNINGS-SPECIFIC FOCUS:
- Extract and highlight: Revenue [DOC: location], EPS [DOC: location], key segment performance
- Identify the primary drivers of performance (mark sources for all claims)
- Note any guidance updates or management outlook changes [DOC: location]
- If Exhibit 99 contains detailed financials, cite it properly [DOC: Exhibit 99]"""
        
        elif item_type and item_type.startswith('1.01'):  # Material Agreement
            type_specific_guidance = """
AGREEMENT-SPECIFIC FOCUS:
- Summarize the key terms with sources: parties involved, duration, financial terms [DOC: Item 1.01]
- Explain the strategic rationale and expected benefits [DOC: location]
- Identify any conditions, milestones, or termination clauses [DOC: agreement section]
- Assess the potential financial and operational impact"""
        
        elif item_type and item_type.startswith('5.02'):  # Executive Changes
            type_specific_guidance = """
LEADERSHIP-SPECIFIC FOCUS:
- Clearly state who is leaving/joining and their roles [DOC: Item 5.02]
- Note effective dates and transition arrangements [DOC: location]
- Include relevant background on new appointees [DOC: biographical section]
- Assess potential impact on strategy or operations"""
        
        # OPTIMIZED: Flexible word count guidance
        return f"""You are a financial journalist analyzing a material event for {company_name} ({ticker}).

{marking_instructions}

CORE MISSION:
Explain this event's significance and likely impact on the company and its investors.

WORD COUNT GUIDANCE:
Target 400-800 words depending on the event's complexity.
A concise 400-word analysis of a straightforward event is better than padding.
Major transactions or complex events may warrant the full 800 words.

CONTENT CONTEXT:
This 8-K filing reports: {event_type}
{f"Item {item_type} disclosure" if item_type else ""}
{f"The filing includes Exhibit 99 with detailed supplementary information - cite it as [DOC: Exhibit 99]" if has_exhibit else ""}

KEY PRINCIPLES:
1. **Event Focus**: What happened and why it matters - cite specific sections
2. **Data Mining**: {f"Extract specific numbers from [DOC: Exhibit 99]" if has_exhibit else "Extract key facts from [DOC: Item sections]"}
3. **Impact Analysis**: Immediate and longer-term implications for the business and stock
4. **News Style**: Direct, factual, implications-focused writing with source marks
5. **Targeted Emphasis**: Use *asterisks* for key data points and **bold** for critical implications

{type_specific_guidance}

ANALYSIS FRAMEWORK:
- Lead with the most newsworthy aspect {f"from [DOC: Exhibit 99]" if has_exhibit else "from the [DOC: Item disclosure]"}
- Provide essential context and details in descending order of importance
- Mark every factual claim with its source
- Explain the business/financial impact with specific examples when available
- Consider the strategic implications and market positioning
- Project likely market reaction and investor considerations
- Close with what to watch for next

REMEMBER: Focus on what's disclosed, not what you wish was disclosed!

CONTEXT:
Event Date: {context.get('filing_date', '')}
{f"Item Type: {item_type}" if item_type else ""}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Analyze this event with complete source attribution."""
    
    def _build_s1_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build reformed prompt for S-1 filings with mandatory data marking"""
        marking_instructions = self._build_data_marking_instructions()
        
        # FIXED: Get company name safely for S-1 (often no ticker yet)
        company_name = filing.company.name if filing.company else "the company"
        ticker = self._get_safe_ticker(filing)
        
        # For S-1, emphasize company name over ticker since many don't have tickers yet
        company_identifier = company_name
        if ticker and ticker not in ["UNKNOWN", "PRE-IPO"] and not ticker.startswith("CIK"):
            company_identifier = f"{company_name} ({ticker})"
        
        # OPTIMIZED: Flexible word count guidance
        return f"""You are an IPO analyst evaluating {company_identifier}'s public offering for potential investors.

{marking_instructions}

CORE MISSION:
Create an analysis that helps investors understand the investment opportunity and risks.

WORD COUNT GUIDANCE:
Target 600-1000 words based on disclosure completeness.
For SPACs or early-stage companies with limited operating history, 600 words focused on structure and risks is appropriate.
Established companies with rich financial history may warrant the full 1000 words.

CONTENT CONTEXT:
This S-1 registration statement includes business overview, risk factors, use of proceeds, and financial information for a company going public.

KEY PRINCIPLES:
1. **Investment Thesis**: What's the opportunity and why should investors care? Mark all claims!
   - If limited financials exist (e.g., SPAC), focus on structure and strategy
2. **Business Reality**: Use specific data from the S-1 with [DOC: section] citations
3. **Balanced View**: Both opportunity and risk deserve thorough attention with sources
4. **IPO Specifics**: Valuation indicators [DOC: location], use of proceeds [DOC: Use of Proceeds], growth trajectory [DOC: Financial Data]
5. **Clear Emphasis**: Use *asterisks* for key metrics and **bold** for critical insights

CRITICAL ELEMENTS TO ADDRESS:
- Business model and competitive position [DOC: Business section]
- Financial trajectory and unit economics [DOC: Financial Statements] (if available)
- Cash burn rate and runway [CALC: based on financials] (if applicable)
- Key risks from Risk Factors section [DOC: Risk Factors]
- Management and governance insights [DOC: Management section]

For SPACs or pre-revenue companies:
- Focus on sponsor track record, target criteria, and structure
- Acknowledge limited operating history explicitly

REMEMBER: A shorter honest assessment beats a longer speculative one!

CONTEXT:
Filing Date: {context.get('filing_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Evaluate this IPO opportunity with complete source citations."""
    
    def _build_generic_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build generic prompt for other filing types with mandatory data marking"""
        marking_instructions = self._build_data_marking_instructions()
        
        # FIXED: Get ticker and company name safely
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        # OPTIMIZED: Flexible word count guidance
        return f"""You are a financial analyst examining this {filing.filing_type.value} filing for {company_name} ({ticker}).

{marking_instructions}

WORD COUNT GUIDANCE:
Target 500-800 words, adjusting to the filing's information density.
A concise 500-word analysis of limited disclosures is preferable to speculation.

Write an analysis that:
1. Identifies the key disclosures and their significance (mark all sources)
2. Explains the implications for investors
3. Uses specific data from the filing with [DOC: location] citations
4. Maintains professional clarity throughout
5. Acknowledges any key information that appears to be missing

Focus on what's material and actionable for investors.
Remember: Accuracy over length!

FILING CONTENT:
{content}"""
    
    def _build_filing_context(self, filing: Filing, analyst_data: Optional[Dict] = None) -> Dict:
        """Build context dictionary for prompt generation"""
        context = {
            'fiscal_year': filing.fiscal_year,
            'fiscal_quarter': filing.fiscal_quarter,
            # FIXED: Use period_end_date instead of period_date
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
        """
        Generate a compelling feed summary from unified analysis
        ENHANCED: Creates 2-3 sentence summaries that are informative and engaging
        """
        # Extract key data points from the unified analysis
        key_numbers = re.findall(r'\*([^*]+)\*', unified_analysis)[:5]
        key_concepts = re.findall(r'\*\*([^*]+)\*\*', unified_analysis)[:3]
        positive_points = re.findall(r'\+\[([^\]]+)\]', unified_analysis)[:2]
        negative_points = re.findall(r'-\[([^\]]+)\]', unified_analysis)[:2]
        
        # Extract the most compelling narrative elements
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
        if filing_type == "FORM_10K":
            prompt = self._build_10k_summary_prompt(filing, narrative_elements, unified_analysis)
        elif filing_type == "FORM_10Q":
            prompt = self._build_10q_summary_prompt(filing, narrative_elements, unified_analysis)
        elif filing_type == "FORM_8K":
            prompt = self._build_8k_summary_prompt(filing, narrative_elements, unified_analysis)
        elif filing_type == "FORM_S1":
            prompt = self._build_s1_summary_prompt(filing, narrative_elements, unified_analysis)
        else:
            prompt = self._build_generic_summary_prompt(filing, narrative_elements, unified_analysis)

        # Generate the compelling summary
        summary = await self._generate_text(prompt, max_tokens=100)
        
        # FIXED: Get ticker safely
        ticker = self._get_safe_ticker(filing)
        
        # Ensure ticker is included
        if ticker not in summary:
            summary = f"{ticker}: {summary}"
        
        # Ensure reasonable length (200-300 chars for 2-3 sentences)
        if len(summary) > 300:
            # Intelligently truncate at sentence boundary
            sentences = summary.split('. ')
            truncated = sentences[0] + '. ' + sentences[1] + '.'
            if len(truncated) <= 300:
                summary = truncated
            else:
                summary = sentences[0] + '...'
        
        # Clean up any data source markers for readability in feed
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
5. End with forward-looking element or question if appropriate
6. Make investors want to read more

Examples of compelling styles:
- Contrast: "AAPL: Record $365B revenue masks declining China sales. Can Vision Pro reverse the trend?"
- Transformation: "MSFT: Cloud revenue jumps 42% as AI pivot accelerates. Traditional software now less than 30% of business."
- Question: "TSLA: Margins compress to 16% despite price cuts. Is market share worth the profit sacrifice?"

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
5. Tease any guidance changes or uncertainties
6. Create urgency or curiosity

Compelling styles:
- Beat/Miss: "AMZN: AWS crushes estimates with 32% growth, but retail margins shrink. Is the cloud party ending?"
- Momentum: "NVDA: Data center revenue explodes 141% as AI demand overwhelms supply. Guidance implies no slowdown."
- Warning: "META: User growth stalls at 2% while costs surge 19%. Reality Labs burns another $3.7B."

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_8k_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build compelling summary prompt for 8-K filings"""
        ticker = self._get_safe_ticker(filing)
        
        # Detect event type from analysis
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
5. Create immediacy and impact
6. Pose a strategic question if relevant

Compelling styles:
- Leadership: "IBM: CEO exits after 3 years amid cloud struggles. Can new leader revive growth as AWS pulls further ahead?"
- M&A: "CRM: Drops $27.7B on Slack despite investor pushback. Integration risk or collaboration goldmine?"
- Earnings: "NFLX: Surprise Q3 beat sends shares up 8%, but password crackdown impact remains unclear."
- Strategic: "DIS: Restructures streaming after $1.5B loss. Is profitability finally within reach?"

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_s1_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build compelling summary prompt for S-1 filings"""
        # FIXED: For S-1, use company name if no ticker
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else ticker
        
        # Use company name for S-1 summaries if ticker is generic
        identifier = company_name if ticker in ["UNKNOWN", "PRE-IPO"] or ticker.startswith("CIK") else ticker
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {identifier}'s IPO filing.

Requirements:
1. Start with identifier: "{identifier}:"
2. Capture what makes this IPO unique or risky
3. Include valuation context or growth rate
4. Highlight the investment tension (growth vs. profitability)
5. Make readers curious about the opportunity
6. Frame as opportunity or warning

Compelling styles:
- High Growth: "Airbnb: Seeking $47B valuation despite 80% revenue drop. Can post-pandemic travel surge justify the premium?"
- Profitability Question: "Uber: $8.5B revenue but still burning $1B quarterly. When does growth translate to profits?"
- Market Opportunity: "Snowflake: Cloud data warehouse targets $81B market. Early losses mask 174% revenue growth trajectory."

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the compelling summary:"""
    
    def _build_generic_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build generic compelling summary prompt"""
        ticker = self._get_safe_ticker(filing)
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s {filing.filing_type.value} filing.

Requirements:
1. Start with ticker: "{ticker}:"
2. Identify the most significant disclosure
3. Explain immediate impact
4. Use specific data points
5. Create reader interest

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
            'sources': []  # NEW: Track source citations
        }
        
        # Extract section headers
        sections = re.findall(r'^##\s+(.+)$', text, re.MULTILINE)
        markup_data['sections'] = sections
        
        # Extract key numbers
        numbers = re.findall(r'\*([^*]+)\*', text)
        markup_data['numbers'] = numbers[:10]
        
        # Extract concepts
        concepts = re.findall(r'\*\*([^*]+)\*\*', text)
        markup_data['concepts'] = concepts[:8]
        
        # Extract positive trends
        positive = re.findall(r'\+\[([^\]]+)\]', text)
        markup_data['positive'] = positive[:5]
        
        # Extract negative trends
        negative = re.findall(r'-\[([^\]]+)\]', text)
        markup_data['negative'] = negative[:5]
        
        # NEW: Extract source citations
        for pattern_name, pattern in DATA_SOURCE_PATTERNS.items():
            matches = re.findall(pattern, text)
            for match in matches[:5]:  # Limit to avoid too much data
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
        
        # Also count data source markings
        markup_patterns.extend(DATA_SOURCE_PATTERNS.values())
        
        markup_chars = 0
        for pattern in markup_patterns:
            matches = re.findall(pattern, text)
            markup_chars += sum(len(match) for match in matches)
        
        density = markup_chars / total_length if total_length > 0 else 0
        
        logger.info(f"Markup density: {density:.2%}")
        
        return text
    
    async def _extract_supplementary_fields(self, filing: Filing, unified_result: Dict, primary_content: str, full_text: str):
        """Extract supplementary fields from unified analysis"""
        unified_text = unified_result['unified_analysis']
        
        # Extract tone from unified analysis
        tone_data = await self._analyze_tone(unified_text)
        filing.management_tone = tone_data['tone']
        filing.tone_explanation = tone_data['explanation']
        
        # FIXED: Use safe ticker and company name
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else "the company"
        
        # Generate questions based on unified analysis
        filing.key_questions = await self._generate_questions_from_unified(
            company_name, filing.filing_type.value, unified_text
        )
        
        # Extract tags from markup data and content
        filing.key_tags = self._generate_tags_from_unified(unified_result['markup_data'], unified_text, filing.filing_type)
        
        # Set ai_summary for backward compatibility
        paragraphs = unified_text.split('\n\n')
        filing.ai_summary = '\n\n'.join(paragraphs[:3])
        
        # Extract key type-specific fields if needed
        if filing.filing_type == FilingType.FORM_10K:
            filing.financial_highlights = await self._extract_financial_highlights(unified_text)
        elif filing.filing_type == FilingType.FORM_10Q:
            filing.financial_highlights = await self._extract_financial_highlights(unified_text)
            if unified_result.get('analyst_data'):
                filing.expectations_comparison = self._format_expectations_comparison(unified_result['analyst_data'])
        elif filing.filing_type == FilingType.FORM_8K:
            filing.event_type = self._identify_8k_event_type(primary_content)
            filing.item_type = self._extract_8k_item_type(primary_content)
        elif filing.filing_type == FilingType.FORM_S1:
            filing.financial_highlights = await self._extract_financial_highlights(unified_text)
    
    async def _analyze_tone(self, content: str) -> Dict:
        """Analyze management tone from unified analysis"""
        prompt = f"""Analyze the tone of this financial analysis. Classify as one of:
- OPTIMISTIC: Positive outlook, growth expectations, confidence
- CONFIDENT: Steady progress, meeting targets, stable outlook  
- NEUTRAL: Balanced view, normal operations, mixed signals
- CAUTIOUS: Some concerns, watchful stance, conservative outlook
- CONCERNED: Significant challenges, risks, negative trends

Analysis excerpt:
{content[:2000]}

Respond with:
TONE: [classification]
EXPLANATION: [2-3 sentence explanation based on specific evidence from the text]"""

        response = await self._generate_text(prompt, max_tokens=150)
        
        # Parse response
        tone = ManagementTone.NEUTRAL  # default
        explanation = ""
        
        if response:
            lines = response.split('\n')
            for line in lines:
                if line.startswith('TONE:'):
                    tone_str = line.replace('TONE:', '').strip()
                    try:
                        tone = ManagementTone[tone_str]
                    except:
                        pass
                elif line.startswith('EXPLANATION:'):
                    explanation = line.replace('EXPLANATION:', '').strip()
        
        return {'tone': tone, 'explanation': explanation}
    
    async def _generate_questions_from_unified(self, company_name: str, filing_type: str, unified_text: str) -> List[Dict]:
        """Generate Q&A from unified analysis"""
        prompt = f"""Based on this {filing_type} analysis for {company_name}, generate 3 important questions investors might ask, with brief answers.

Analysis excerpt:
{unified_text[:1500]}

Format each as:
Q: [Specific question about the filing]
A: [Brief factual answer based on the analysis, 2-3 sentences]

Focus on material issues raised in the analysis."""

        response = await self._generate_text(prompt, max_tokens=400)
        
        questions = []
        if response:
            qa_pairs = response.split('\n\n')
            for pair in qa_pairs:
                if 'Q:' in pair and 'A:' in pair:
                    parts = pair.split('\nA:')
                    if len(parts) == 2:
                        question = parts[0].replace('Q:', '').strip()
                        answer = parts[1].strip()
                        questions.append({'question': question, 'answer': answer})
        
        return questions[:3]
    
    def _generate_tags_from_unified(self, markup_data: Dict, unified_text: str, filing_type: FilingType) -> List[str]:
        """Generate tags from unified analysis and markup data"""
        tags = []
        text_lower = unified_text.lower()
        
        # Add tags based on markup content
        if markup_data['positive']:
            if any('beat' in item.lower() or 'exceed' in item.lower() for item in markup_data['positive']):
                tags.append('Earnings Beat')
            if any('growth' in item.lower() for item in markup_data['positive']):
                tags.append('Growth')
        
        if markup_data['negative']:
            if any('miss' in item.lower() or 'below' in item.lower() for item in markup_data['negative']):
                tags.append('Earnings Miss')
            if any('decline' in item.lower() or 'down' in item.lower() for item in markup_data['negative']):
                tags.append('Declining Metrics')
        
        # Content-based tags
        if any('margin' in concept.lower() for concept in markup_data['concepts']):
            tags.append('Margins')
        if 'guidance' in text_lower:
            tags.append('Guidance Update')
        if any(word in text_lower for word in ['dividend', 'buyback', 'repurchase']):
            tags.append('Capital Return')
        if any(word in text_lower for word in ['acquisition', 'merger', 'm&a']):
            tags.append('M&A Activity')
        
        # Filing type tag
        if filing_type == FilingType.FORM_10K:
            tags.append('Annual Report')
        elif filing_type == FilingType.FORM_10Q:
            tags.append('Quarterly Results')
        elif filing_type == FilingType.FORM_8K:
            tags.append('Material Event')
        elif filing_type == FilingType.FORM_S1:
            tags.append('IPO')
            
        return list(set(tags))[:5]
    
    async def _extract_financial_highlights(self, unified_text: str) -> str:
        """Extract financial highlights from unified analysis"""
        prompt = f"""Extract the key financial metrics and create a brief financial highlights summary.

Analysis:
{unified_text[:2000]}

Create a 100-150 word summary focusing on:
- Revenue and growth figures
- Profitability metrics
- Key operational metrics
- Any other critical financial data

Write in clear, flowing prose - not bullet points. Be specific with numbers."""

        return await self._generate_text(prompt, max_tokens=200)
    
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
        
        # Check for Item numbers first for more accurate classification
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
        elif 'item 5.03' in content_lower:
            return "Bylaw/Charter Amendment"
        elif 'item 3.01' in content_lower:
            return "Delisting Notice"
        elif 'item 4.01' in content_lower:
            return "Accountant Change"
        
        # Fallback to content-based detection
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
        """Generate text using OpenAI with configured temperature"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst with expertise in SEC filings analysis. Write in clear, professional English suitable for sophisticated retail investors. Always cite your sources."},
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