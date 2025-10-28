# app/services/ai_processor.py
"""
AI Processor Service - Enhanced with Flash Note Style for o3-mini
Version: v11_o3mini
MAJOR UPDATE: 
- Switched to o3-mini reasoning model
- Restructured 10-Q prompt with Sell-Side Flash Note style
- Enhanced beat/miss calculation workflow to prevent AI失焦
- Optimized for autonomous web search and tool use
- NEW v11: Role-driven concise summaries (120-180 chars)
- NEW v11: Pure role definition without artificial examples
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
        
        self.max_input_tokens = 100000
        self.target_output_tokens = 3000
    
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
            not company.pe_ratio or 
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
                
                pe_ratio = fmp_data.get('pe_ratio')
                if not pe_ratio:
                    key_metrics = fmp_service.get_company_key_metrics(ticker)
                    if key_metrics and key_metrics.get('pe_ratio'):
                        pe_ratio = key_metrics['pe_ratio']
                
                if pe_ratio and pe_ratio > 0:
                    company_updates['pe_ratio'] = pe_ratio
                
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
        ✅ NEW: Enhanced 10-Q prompt with Flash Note style for o3-mini
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

{critical_estimates}{marking_instructions}

## OUTPUT STRUCTURE (MANDATORY)

---

### SECTION 1: FACT CLARITY

**Format Requirements**:

1. **Headline** (MANDATORY - First Line):
   - 8-15 words maximum
   - Capture: Beat/Miss + Key Driver + Action Implication
   - Examples:
     * "TICKER Beats on EPS (+XX% YoY); Strong Category Recovery Drives Upside"
     * "TICKER Misses on Margins; Guidance Cut Pressures Valuation"

2. **Bullet Points** (8-12 bullets):
   - Each bullet = One metric only
   - Format: `• **Metric Name**: $XX.XB, +X% YoY [Source] - Commentary`
   - Use abbreviations: YoY, QoQ, v/s
   - Bold **BEAT** or **MISS** vs. consensus when applicable [FMP]
   - Most important metrics first (Revenue, EPS always top 2)
   
   **MANDATORY FIRST TWO BULLETS** (if estimates available):
   • **Total Revenue**: $XX.XB, +X% YoY [DOC: Income Statement] - **BEAT/MISS** by $X.XB vs. estimate [FMP]
   • **Diluted EPS**: $X.XX, +X% YoY [DOC] - **BEAT/MISS** by $X.XX vs. consensus [FMP]

3. **Length**: 300-450 words maximum

**Quality Bar**: 
Would a trader understand the key numbers and beat/miss in one quick scan?

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

1. **Structure** (Natural Prose Paragraphs):
   - Paragraph 1: Why beat/miss happened + peer comparison (search if needed)
   - Paragraph 2: Margin/profitability drivers
   - Paragraph 3: Key operational metrics or risk factors
   - Paragraph 4-5: Forward catalysts/concerns
   - Final Paragraph: "Bottom Line" summary

2. **Length**: 600-800 words (strict max: 900 words)

3. **External Context**:
   - You have web search capability
   - Use when industry/peer context adds material insight
   
   **WHEN to search** (Concrete Examples):
   ✅ "Competitor's Q3 revenue growth for comparison"
   ✅ "Industry-wide credit delinquency trends"
   ✅ "Peer company's recent earnings results"
   ❌ Don't search for generic statements like "industry is growing"
   ❌ Don't search if filing already provides sufficient context
   
   **CITATION REQUIREMENTS** (CRITICAL):
   - Every search result MUST be cited as [1], [2], [3]
   - At bottom of Section 2, list full sources:
     Example format:
     [1] Competitor Name Q3 2025 Earnings Release, Month Year
     [2] Federal Reserve Report Name, Month Year
   - NO citations without full source details
   - NO vague references like "according to industry data"

4. **Data Attribution**: 
   - Same rules as Section 1
   - Every claim needs source

**Quality Bar**:
Would a PM trust this enough to increase position size by 2%?

---

## CRITICAL RULES

**Data Source Attribution** (MANDATORY):
- [DOC: Location] - From this filing
- [FMP] - Analyst consensus (pre-provided)
- [CALC: formula] - Your calculations
- [1], [2] - Web search (with full source at bottom)

**Style**:
- Active voice: "Revenue grew 11%" not "was up 11%"
- Specific: "$XX.XB" not "approximately XX billion"
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

**SECTION 1: FACT CLARITY** - Headline + 8-12 bullets (max 450 words)
**SECTION 2: MARKET PERSPECTIVE** - Analyst commentary (600-800 words)
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
        10-K prompt - Annual fundamentals review for retail investors
        Structure: ANNUAL REVIEW + STRATEGIC OUTLOOK
        """
        marking_instructions = self._build_data_marking_instructions()
        
        return f"""You are a financial analyst writing an annual report summary for retail investors.

Your readers want to understand: How did the company perform this year? What's the strategy going forward? What are the key risks?

## CORE PRINCIPLE: Facts and Data Drive Your Analysis

Your job is to identify what's IMPORTANT in THIS filing, not to fill in a template blindly.

- If revenue growth is the big story, spend more words explaining it
- If a new risk factor is material, dive deeper into why it matters  
- If margins improved significantly, show the numbers and explain why
- Let the actual content guide your focus, not arbitrary rules

Think like an analyst reading the real document: What jumped out at you? What would investors care most about? Follow the story the data tells you.

Don't force content into boxes - write what matters.

{marking_instructions}

## OUTPUT STRUCTURE (MANDATORY)

---

### SECTION 1: ANNUAL REVIEW

**Purpose**: Help investors understand the company's full-year performance (3 minute read)

**Format**: Natural prose paragraphs (400-600 words)

**What to cover**:

Start with the financial headline: How did revenue, profit, and cash flow perform compared to last year? Use the 3-year data from the financial statements and MD&A.

Then explain what drove the results: Which products/segments grew or declined? What did management say about the performance drivers in MD&A?

Discuss profitability: How did margins change? What happened to operating expenses?

Cover the balance sheet: Cash position, debt levels, how they used their cash (buybacks, dividends, investments)?

If there are important accounting changes or one-time items mentioned in the Notes, explain them clearly.

**Data Sources**:
- [DOC: Consolidated Statements of Operations] - Income statement
- [DOC: MD&A - Results of Operations] - Management's explanation  
- [DOC: Consolidated Balance Sheets] - Balance sheet
- [DOC: Statements of Cash Flows] - Cash flow
- [DOC: Notes to Financial Statements] - If applicable

**Style**:
- Write like you're explaining to a friend who invests but isn't a finance expert
- Use clear language: "gross profit margin" not "gross margin compression dynamics"
- Lead with numbers: "Revenue grew 15% to $5.2B" not "The company experienced revenue growth"
- Compare to prior year: "vs. $4.5B last year"

**Quality Bar**: 
A retail investor should understand what happened financially this year without reading the full 10-K.

---

### SECTION 2: STRATEGIC OUTLOOK

**Purpose**: Help investors evaluate the company's future direction and risks (5-7 minute read)

**Format**: Natural prose paragraphs (600-900 words)

**What to cover**:

Start with management's strategy: Based on the MD&A and Business section, what is management focused on? What are they investing in? How are they adapting to market changes?

Discuss competitive position: How is the company positioned in its industry? What advantages does it have? You can search for competitor performance if helpful for context.

Analyze key risks: Pick the 3-5 most important risks from the Risk Factors section - don't just list them, explain why they matter and how likely they are to impact the business.

Look at management's outlook: What did they say about the coming year in MD&A? Any guidance or commentary on trends?

End with key observations: What are the most important things investors should know from this annual report? What should they watch for in the coming year?

**External Context** (Optional):
- You can use web search if industry/competitor context adds value
- Example: Search for "competitor earnings 2024" or "industry growth rate 2024"
- If you search, cite as [1], [2] and list sources at the end:
  [1] Source Title, Publisher, Date
  [2] Source Title, Publisher, Date

**Data Sources**:
- [DOC: MD&A - Business Outlook]
- [DOC: Item 1 - Business]  
- [DOC: Risk Factors]
- [1], [2] if web search used

**Style**:
- Keep it conversational but professional
- Explain jargon: "EBITDA (earnings before interest, taxes, depreciation, amortization)"
- Use analogies if helpful: "Think of free cash flow as the money left after paying all bills"
- Be balanced: mention both positives and concerns

**Quality Bar**:
An investor should be able to decide whether this company fits their investment goals after reading this section.

---

## CRITICAL RULES

**What to AVOID**:
- Don't make investment recommendations: No "Buy", "Sell", "Good for growth investors"
- Don't repeat information between Section 1 and Section 2
- Don't use marketing language: "game-changing", "revolutionary", "best-in-class"
- Don't speculate beyond what's in the filing

**Style**:
- Active voice: "Revenue grew 15%" not "Revenue was up 15%"
- Specific numbers: "$5.2B" not "approximately $5 billion"  
- Clear comparisons: "up from $4.5B last year"
- Plain English: avoid unnecessary jargon

---

## COMPANY CONTEXT

- **Company**: {context['company_name']} ({context['ticker']})
- **Fiscal Year**: {context.get('fiscal_year', '2024')}
- **Filing Date**: {context['filing_date']}

---

## FILING CONTENT

{content}

---

Now generate your two-section analysis following this structure.

**SECTION 1: ANNUAL REVIEW** - Natural paragraphs (400-600 words)
**SECTION 2: STRATEGIC OUTLOOK** - Natural paragraphs (600-900 words)

Remember: Write for retail investors who want to understand the company, not for Wall Street professionals.
"""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """
        8-K prompt using Financial News Analyst style
        Structure: EVENT SNAPSHOT + IMPACT ANALYSIS
        """
        marking_instructions = self._build_data_marking_instructions()
        
        # Special handling for Item 2.02 (Earnings Release)
        # Check if this is an earnings-related 8-K
        is_earnings_8k = 'item 2.02' in content.lower() or 'results of operations' in content.lower()
        
        if is_earnings_8k:
            # Use 10-Q style prompt for earnings 8-Ks
            logger.info("Detected Item 2.02 earnings 8-K, using 10-Q prompt structure")
            return self._build_10q_unified_prompt_enhanced(filing, content, context)
        
        # Standard 8-K prompt for other material events
        return f"""You are a financial news analyst covering breaking corporate events for {context['company_name']}.

A material 8-K filing just hit the wire. Your institutional clients need:
1. Fast: What happened?
2. Clear: Why it matters?
3. Actionable: What should I watch?

{marking_instructions}

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

**Examples of good Lede paragraphs**:

For M&A:
"Company signed a definitive agreement to acquire Target for $X.XB in cash 
and stock, disclosed in an 8-K filing Monday [DOC: Item 1.01]. The transaction 
marks Company's largest acquisition since 20XX."

For Executive Change:
"Company announced the resignation of CFO Name effective Date, disclosed 
Tuesday [DOC: Item 5.02]. The board appointed Successor as interim CFO while 
conducting a search for a permanent successor."

For Debt Issuance:
"Company priced $X.XB of senior unsecured notes in a two-tranche offering, 
announced Friday [DOC: Item 2.03, Exhibit 99.1]. Proceeds will fund expansion 
and general corporate purposes."

---

### SECTION 2: IMPACT ANALYSIS

**Purpose**: Explain why this event matters and what comes next

**Format**: Natural prose paragraphs (500-700 words)

**Structure**: Flexible based on event complexity, but typically includes:

**Paragraph 1 - Strategic Rationale**: Why did management do this? Why now?
- What problem does this solve or opportunity does it capture?
- How does this fit the company's stated strategy?
- Based on [DOC: Item X.XX, Exhibit 99.1] and management commentary if available

**Paragraph 2 - Financial Implications**: Impact on the business
- How does this affect revenue, costs, cash flow, balance sheet?
- Use specific numbers from the filing [DOC:]
- Calculate if needed [CALC:] - e.g., impact on EPS, debt ratios

**Paragraph 3 - Market Context**: How does this compare? (Search when relevant)
- For M&A: Search for comparable recent transactions in the sector
- For executive changes: Search for successor's track record at prior companies
- For debt: Search for current market rates and peer borrowing costs
- For partnerships: Search for similar deals by competitors
- Only search when external context materially enhances understanding

**Paragraph 4 - Forward Looking**: Risks, opportunities, what to watch
- Execution risks or regulatory hurdles
- Upside scenarios
- Key milestones or triggers to monitor
- Management credibility on similar past actions

**WHEN TO SEARCH** (Use your judgment):
✅ M&A deal → search for "recent {{industry}} acquisitions valuation multiples"
✅ Executive change → search for "{{successor name}} background track record"
✅ Debt issuance → search for "corporate bond yields {{industry}} 2025"
✅ Material agreement → search for "competitor similar partnerships"
❌ Don't search if the 8-K filing itself provides comprehensive context
❌ Don't search for generic background that doesn't add insight

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
"""
    
    def _build_s1_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """
        S-1 prompt - IPO analysis for retail investors
        Structure: IPO SNAPSHOT + INVESTMENT ANALYSIS
        """
        marking_instructions = self._build_data_marking_instructions()
        
        # Handle pre-IPO companies without tickers
        ticker = self._get_safe_ticker(filing)
        company_name = context['company_name']
        
        return f"""You are a financial analyst explaining an IPO filing to retail investors.

Your readers want to understand: What does this company do? How's the business performing? Should I look deeper into this IPO?

## CORE PRINCIPLE: Facts and Data Drive Your Analysis

Your job is to identify what's IMPORTANT in THIS S-1 filing, not to follow a rigid checklist.

- If the company has explosive growth, show the numbers and explain what's driving it
- If there's a major customer concentration risk, spend time explaining the impact
- If the underwriters are top-tier banks, that's worth noting (it signals quality)
- If pre-IPO investors include well-known VCs, mention them - it's a trust signal
- Let the actual filing content guide what you emphasize

Think like an analyst evaluating a real IPO: What stands out? What are the key questions investors should ask? Follow what the data reveals.

Don't force every IPO into the same template - each story is different.

{marking_instructions}

## OUTPUT STRUCTURE (MANDATORY)

---

### SECTION 1: IPO SNAPSHOT

**Purpose**: Help investors quickly understand what this IPO is about (3 minute read)

**Format**: Natural prose with one bullet section (350-500 words)

**What to cover**:

Start with the business: What does this company do? How do they make money? Who are their customers? Keep it simple - explain it like you're telling a friend about a new company going public.

Show the financial trajectory: How has revenue grown over the past 2-3 years? Are they profitable or losing money? If losing money, what's the cash burn rate? Use the financial statements.

Explain the market opportunity: What market are they in? How big is the opportunity? Use data from the Business section if provided.

Then use a clean bullet format for the deal details:

• **Offering Size**: XX million shares at $XX-XX per share [DOC: Prospectus Summary]
• **Expected Proceeds**: $XXM - $XXM [DOC: Use of Proceeds]
• **Main Use of Proceeds**: [List 2-3 key uses in plain language] [DOC: Use of Proceeds]
• **Lead Underwriters**: [List the main investment banks - e.g., Goldman Sachs, Morgan Stanley] [DOC: Underwriting]
  (Note: Top-tier underwriters signal institutional confidence in the deal)
• **Major Pre-IPO Investors**: [List top 3-5 with ownership % - e.g., Sequoia Capital 18.2%, Andreessen Horowitz 12.5%] [DOC: Principal Stockholders]
  (Note: Well-known venture capital backing can indicate quality, though not a guarantee)

**Data Sources**:
- [DOC: Business] - Company description
- [DOC: Consolidated Statements of Operations] - Financial history
- [DOC: Prospectus Summary] - Deal terms
- [DOC: Use of Proceeds] - How they'll use the money
- [DOC: Underwriting] - Banks managing the IPO
- [DOC: Principal Stockholders] - Who owns the company now

**Style**:
- Explain the business model clearly: "They charge subscription fees" not "monetize via recurring revenue streams"
- Show growth with simple numbers: "Revenue went from $100M to $500M over 3 years"
- Make the bullets scannable - investors want to see the deal terms quickly

**Quality Bar**:
An investor should understand the business and deal basics without any prior knowledge of the company.

---

### SECTION 2: INVESTMENT ANALYSIS  

**Purpose**: Help investors evaluate whether this IPO deserves deeper research (7-10 minute read)

**Format**: Natural prose paragraphs (600-800 words)

**What to cover**:

Assess the growth story: Is the revenue growth sustainable? What's driving it? Look at customer metrics, repeat business, expansion plans from the MD&A and Business sections.

If the company is unprofitable: When might they reach profitability? What needs to happen? Are margins improving?

Discuss the competitive landscape: Who are the competitors? What makes this company different? Use the Business section's competition discussion. You can search for competitor info if helpful.

Analyze the key risks: Pick the 3-5 most important risks from Risk Factors - explain them in plain language and why they matter. For example: "The company gets 40% of revenue from its top 3 customers - losing one would significantly hurt results."

Evaluate the team: Does the management team have relevant experience? Check the Management section for backgrounds.

Consider the backing: The quality of underwriters and pre-IPO investors can be informative signals. Top investment banks (like Goldman Sachs, J.P. Morgan) do extensive due diligence before taking companies public. Well-known venture capital firms (like Sequoia, Andreessen Horowitz) typically invest after deep research. However, strong backing doesn't guarantee success - it's one factor among many. Note if there are any red flags like very small or unknown underwriters.

End with key observations: What are the most important things to know about this IPO? What questions should investors research further before deciding?

**External Context** (Optional):
- Search for similar companies' IPO performance or valuations if helpful
- Search for industry growth trends or market data
- If you search, cite as [1], [2] and list sources at the end:
  [1] Source Title, Publisher, Date
  [2] Source Title, Publisher, Date

**Data Sources**:
- [DOC: Business]
- [DOC: Risk Factors]  
- [DOC: Management]
- [DOC: MD&A]
- [1], [2] if web search used

**Style**:
- Keep it accessible: "burn rate" → "how fast they're spending cash"
- Be honest about risks - IPOs are risky investments
- Explain financial concepts: "dilution means your ownership percentage goes down"
- Stay neutral - present information, don't recommend

**Quality Bar**:
An investor should have enough information to decide if they want to do more research on this IPO.

---

## CRITICAL RULES

**What to AVOID**:
- Don't make investment recommendations: No "This is a good IPO" or "Wait for a better price"
- Don't say things like "suitable for aggressive investors" - that's investment advice
- Don't repeat information between Section 1 and Section 2
- Don't use hype language: "disruptive", "revolutionary", "game-changing"
- Don't speculate beyond what's disclosed

**Style**:
- Active voice: "The company operates" not "is operated"
- Clear numbers: "$500M revenue" not "half a billion in top-line"
- Plain language: "profit margin" not "EBITDA margin expansion trajectory"  
- Conversational but professional

---

## COMPANY CONTEXT

- **Company**: {company_name}
- **Ticker**: {ticker} (or "Pre-IPO" if not assigned yet)
- **Filing Date**: {context['filing_date']}
- **IPO Status**: Registration filed, pricing pending

---

## FILING CONTENT

{content}

---

Now generate your two-section analysis following this structure.

**SECTION 1: IPO SNAPSHOT** - Prose + bullet section (350-500 words)
**SECTION 2: INVESTMENT ANALYSIS** - Natural paragraphs (600-800 words)

Remember: Write for retail investors who are curious about this IPO but need clear, honest information to evaluate it.
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
        
        filing.key_tags = self._generate_enhanced_tags(unified_result['markup_data'], unified_text, filing.filing_type, ticker)
        
        filing.management_tone = None
        filing.tone_explanation = None
        filing.key_questions = []
        filing.financial_highlights = None
        filing.ai_summary = None
        
        if filing.filing_type == FilingType.FORM_8K:
            filing.event_type = self._identify_8k_event_type(primary_content)
            filing.item_type = self._extract_8k_item_type(primary_content)
    
    def _generate_enhanced_tags(self, markup_data: Dict, unified_text: str, filing_type: Union[FilingType, str], ticker: str) -> List[str]:
        """Generate tags"""
        tags = []
        text_lower = unified_text.lower()
        
        industry_keywords = {
            'Technology': ['software', 'cloud', 'saas', 'platform', 'digital', 'ai'],
            'Healthcare': ['drug', 'clinical', 'fda', 'patient'],
            'Financial': ['banking', 'loan', 'deposit'],
            'Retail': ['store', 'e-commerce', 'consumer'],
            'Energy': ['oil', 'gas', 'renewable'],
        }
        
        for industry, keywords in industry_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                tags.append(industry)
                break
        
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
        
        filing_type_key = self._get_safe_filing_type_value(filing_type) if not isinstance(filing_type, str) else filing_type
        if filing_type_key in filing_type_tags:
            tags.append(filing_type_tags[filing_type_key])
        
        tags = list(dict.fromkeys(tags))[:7]
        return tags
    
    def _identify_8k_event_type(self, content: str) -> str:
        """Identify 8-K event type"""
        content_lower = content.lower()
        
        if 'item 2.02' in content_lower:
            return "Earnings Release"
        elif 'item 1.01' in content_lower:
            return "Material Agreement"
        elif 'item 5.02' in content_lower:
            return "Executive Change"
        elif 'results of operations' in content_lower:
            return "Earnings Release"
        else:
            return "Corporate Event"
    
    def _extract_8k_item_type(self, content: str) -> Optional[str]:
        """Extract 8-K item number"""
        item_pattern = r'Item\s+(\d+\.\d+)'
        match = re.search(item_pattern, content, re.IGNORECASE)
        return match.group(1) if match else None


# Initialize singleton
ai_processor = AIProcessor()