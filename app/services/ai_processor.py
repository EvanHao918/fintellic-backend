# app/services/ai_processor.py
"""
AI Processor Service - Enhanced with Web Search Integration
Version: v8_web_search
MAJOR UPDATE: Integrated gpt-4o-search-preview with web search capability
REMOVED: FMP analyst data dependencies
ADDED: Web search references processing and citation system
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

# ✅ UPDATED: Enhanced data source marking patterns with web search citations
DATA_SOURCE_PATTERNS = {
    'document': r'\[DOC:\s*([^\]]+)\]',
    'search': r'\[(\d+)\]',  # NEW: Footnote-style citations for web search
    'calc': r'\[CALC:\s*([^\]]+)\]',
    'no_data': r'\[NO_DATA\]',
    'caution': r'\[CAUTION\]'
}

class AIProcessor:
    """
    Process filings using OpenAI with web search integration
    v8_web_search: Removed FMP analyst data, added web search capability
    """
    
    def __init__(self):
        self.model = settings.AI_MODEL  # Now gpt-4o-search-preview
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        self.enable_web_search = settings.WEB_SEARCH_ENABLED
        
        # Initialize tokenizer
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4o")  # Use gpt-4o encoding
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Token limits
        self.max_input_tokens = 100000
        self.target_output_tokens = 3000
    
    def _get_safe_filing_type_value(self, filing_type: Union[FilingType, str]) -> str:
        """Safely get filing type value, handling both enum and string types"""
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
        Enhanced to support web search citations [1][2][3]
        """
        issues = []
        
        # Extract all numbers and claims
        numbers = re.findall(r'\$[\d,]+[BMK]?|[\d,]+%|\d+\.?\d*\s*(?:million|billion)', text)
        
        # Check if numbers have nearby citations
        unmarked_numbers = 0
        for number in numbers[:15]:
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
                if unmarked_numbers <= 3:
                    issues.append(f"Unmarked number: {number}")
        
        # Check minimum marking density
        total_markings = sum(
            len(re.findall(pattern, text)) 
            for pattern in DATA_SOURCE_PATTERNS.values()
        )
        
        text_length = len(text)
        if text_length > 1000:
            expected_markings = max(5, text_length // 500)
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
        """Intelligently truncate content while preserving key sections"""
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
        """Process a filing using unified AI analysis with web search capability"""
        try:
            filing.status = ProcessingStatus.ANALYZING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            ticker = self._get_safe_ticker(filing)
            company_name = filing.company.name if filing.company else "Unknown Company"
            filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
            
            logger.info(f"Starting v8 web search AI processing for {ticker} {filing_type_value}")
            
            # Fetch and store FMP company profile data
            await self._fetch_and_store_fmp_data(db, filing, ticker)
            
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
            
            # 8-K Exhibit Content Integration
            if filing.filing_type == FilingType.FORM_8K:
                exhibit_content = sections.get('important_exhibits_content', '') or sections.get('exhibit_99_content', '')
                if exhibit_content and len(exhibit_content) > 100:
                    logger.info(f"Integrating exhibit content: {len(exhibit_content)} chars")
                    primary_content += f"\n\n{'='*60}\nEXHIBIT CONTENT (PRESS RELEASE/FINANCIAL DATA)\n{'='*60}\n\n{exhibit_content}"
            
            if not primary_content or len(primary_content) < 100:
                raise Exception("Insufficient text content extracted")
            
            logger.info(f"Extracted content - Primary: {len(primary_content)} chars")
            
            # ❌ REMOVED: FMP analyst data fetching logic
            # Web search will handle analyst expectations dynamically
            
            # Generate unified analysis with web search
            unified_result = await self._generate_unified_analysis_with_retry(
                filing, primary_content, full_text
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.references = unified_result.get('references', [])  # ✅ NEW: Store references
            filing.analysis_version = "v8_web_search"  # ✅ NEW: Updated version marker
            
            # Extract supplementary fields
            await self._extract_supplementary_fields(filing, unified_result, primary_content, full_text)
            
            # Set status
            filing.status = ProcessingStatus.COMPLETED
            filing.processing_completed_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"✅ v8 web search AI processing completed for {filing.accession_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error in v8 web search AI processing: {e}")
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            return False
    
    async def _fetch_and_store_fmp_data(self, db: Session, filing: Filing, ticker: str):
        """Fetch FMP company profile data for enrichment (not for AI analysis)"""
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
    
    async def _generate_unified_analysis_with_retry(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str
    ) -> Dict:
        """Generate unified analysis with web search and intelligent retry logic"""
        max_retries = 3
        
        for attempt in range(max_retries):
            logger.info(f"Analysis attempt {attempt + 1}/{max_retries}")
            
            processed_content = self._preprocess_content_for_ai(
                primary_content, full_text, filing.filing_type, attempt
            )
            
            # Generate analysis with web search
            unified_result = await self._generate_unified_analysis(
                filing, processed_content, processed_content
            )
            
            # Validate data marking
            is_valid, validation_issues = self._validate_data_marking(unified_result['unified_analysis'])
            
            if not is_valid:
                logger.warning(f"Data marking validation failed (attempt {attempt + 1}): {validation_issues}")
                if attempt < max_retries - 1:
                    continue
            
            # Validate word count
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
        """Preprocess content to ensure AI gets high-quality input"""
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
        
        return content.strip()
    
    def _validate_content_quality(self, analysis: str, filing_type: Union[FilingType, str]) -> bool:
        """Validate that the generated analysis has sufficient quality"""
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
        """Check if analysis contains suspicious template numbers"""
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
        """
        Generate unified analysis with web search capability
        ❌ REMOVED: analyst_data parameter
        """
        content = primary_content
        
        filing_context = self._build_filing_context(filing)
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        # Generate unified analysis with filing-specific prompts
        if filing_type_value in ['FORM_10K', '10-K']:
            prompt = self._build_10k_unified_prompt_enhanced(filing, content, filing_context)
        elif filing_type_value in ['FORM_10Q', '10-Q']:
            prompt = self._build_10q_unified_prompt_enhanced(filing, content, filing_context)
        elif filing_type_value in ['FORM_8K', '8-K']:
            prompt = self._build_8k_unified_prompt(filing, content, filing_context)
        elif filing_type_value in ['FORM_S1', 'S-1']:
            prompt = self._build_s1_unified_prompt_enhanced(filing, content, filing_context)
        else:
            prompt = self._build_generic_unified_prompt(filing, content, filing_context)
        
        prompt_tokens = self._count_tokens(prompt)
        logger.info(f"Prompt tokens: {prompt_tokens}")
        
        # ✅ UPDATED: Generate with web search support
        unified_analysis, references = await self._generate_text_with_search(
            prompt, 
            max_tokens=settings.AI_UNIFIED_ANALYSIS_MAX_TOKENS
        )
        
        # Generate feed summary
        feed_summary = await self._generate_feed_summary_from_unified(
            unified_analysis, 
            filing_type_value,
            filing
        )
        
        # Extract markup data
        markup_data = self._extract_markup_data(unified_analysis)
        
        return {
            'unified_analysis': unified_analysis,
            'feed_summary': feed_summary,
            'markup_data': markup_data,
            'references': references  # ✅ NEW: Return references
        }
    
    def _build_filing_context(self, filing: Filing) -> Dict:
        """
        Build context dictionary for prompt generation
        ❌ REMOVED: analyst_data parameter
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
        
        if filing.filing_type == FilingType.FORM_8K:
            context['event_type'] = self._identify_8k_event_type(filing.primary_content if hasattr(filing, 'primary_content') else '')
            context['item_type'] = filing.item_type if hasattr(filing, 'item_type') else ''
            
        return context
    
    def _build_data_marking_instructions(self) -> str:
        """
        Build instructions for data source marking with web search support
        ✅ UPDATED: Added web search citation guidance
        """
        return """
CRITICAL: Data Source Attribution System
=========================================
Every factual claim MUST be attributed to its source using these tags:

1. [DOC: location] - Information from THIS filing document
   Examples: [DOC: Income Statement], [DOC: MD&A p.3], [DOC: Risk Factors]

2. [1], [2], [3]... - Web search results (numbered footnotes)
   - Use for ALL external data: industry trends, competitor metrics, analyst expectations
   - Numbers correspond to References section auto-generated at document end
   - Example: "Industry grew 8% [1], outpacing expectations [2]..."

3. [CALC: formula] - Your calculations from filing data
   Example: [CALC: $15.0B/$13.6B - 1 = 10% YoY growth]

4. [NO_DATA] - When specific information is unavailable
   Example: "Detailed segment breakdown [NO_DATA] in this quarter"

5. [CAUTION] - For inferences with uncertainty
   Example: "This suggests [CAUTION] potential pricing power erosion"

SEARCH GUIDANCE:
- You have access to real-time web search
- Search when external context adds material insight (industry data, peer performance, analyst expectations, macro trends)
- Prioritize authoritative sources: Bloomberg, Reuters, industry research firms
- Do NOT search for information that should be in the filing itself

CRITICAL RULES:
- Financial figures without [DOC:] or [CALC:] tags will be REJECTED
- Web-sourced claims without [1][2][3] citations will be REJECTED
- Markdown tables in filing are your most reliable data source
- Never invent consensus figures - search for them or use [NO_DATA]
"""
    
    # ✅ UPDATED: All prompt building methods now reference web search capability
    # The prompts are loaded from the separate template document you provided
    # I'll include the key prompt methods here with web search integration
    
    def _build_10k_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """Enhanced 10-K prompt with web search guidance"""
        marking_instructions = self._build_data_marking_instructions()
        
        return f"""You are a seasoned equity analyst writing for retail investors who want professional insights in accessible language.

{marking_instructions}

CORE MISSION: 
Create a comprehensive analysis of this annual report that helps readers understand {context['company_name']} ({context['ticker']}) year in review, future prospects, and management effectiveness.

When peer comparison or industry context would enrich your analysis, you may search for:
- Industry growth rates and market size data
- Peer group performance metrics
- Sector trends and competitive dynamics
- Analyst perspectives on the company or industry

WORD COUNT GUIDANCE:
Aim for 800-1200 words if the filing provides rich information.

CRITICAL ANALYSIS AREAS:
1. **Financial Performance** - Revenue, profitability, cash flow with [DOC:] citations
2. **Management Discussion** - Strategic priorities and outlook [DOC: MD&A]
3. **Industry Context** - Search for relevant market data when helpful [1][2]
4. **Competitive Position** - How does this company compare? [DOC: + search]
5. **Risk Assessment** - Top material risks [DOC: Risk Factors]

CONTEXT:
Company: {context['company_name']} ({context['ticker']})
Fiscal Year: {context.get('fiscal_year', 'FY2024')}
Current Date: {context['current_date']}

FILING CONTENT:
{content}

Provide comprehensive analysis with complete source attribution:"""
    
    def _build_10q_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """
        Enhanced 10-Q prompt with web search for analyst expectations
        ❌ REMOVED: analyst_data parameter and FMP context
        """
        marking_instructions = self._build_data_marking_instructions()
        
        return f"""You are a professional equity analyst writing for retail investors seeking clear quarterly insights.

{marking_instructions}

CORE MISSION:
Analyze {context['company_name']}'s ({context['ticker']}) quarterly results: What happened? Why does it matter? What's management saying?

When analyst expectations or peer comparisons would add context, search for:
- Analyst consensus for revenue/EPS for this quarter
- Peer quarterly results announced recently
- Industry quarterly trends and data

WORD COUNT GUIDANCE:
Target 600-1000 words based on available information.

CRITICAL ANALYSIS AREAS:
1. **Quarterly Performance** - Results vs prior year/quarter [DOC: Financial Statements]
2. **Beat/Miss Analysis** - Compare to expectations if found via search [1][2]
3. **Management Commentary** - Guidance and outlook [DOC: MD&A]
4. **Operational Trends** - Margins, segments, key metrics [DOC:]
5. **Industry Context** - How did peers perform? [search when helpful]

CONTEXT:
Company: {context['company_name']} ({context['ticker']})
Quarter: {context.get('fiscal_quarter', 'Q3 2024')}
Current Date: {context['current_date']}

If you cannot find analyst expectations via search, use [NO_DATA] and focus on sequential and YoY comparisons.

FILING CONTENT:
{content}

Analyze this quarter's performance with complete source attribution:"""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """8-K prompt with web search for event context"""
        marking_instructions = self._build_data_marking_instructions()
        
        return f"""You are a financial journalist analyzing a material event for {context['company_name']} ({context['ticker']}).

{marking_instructions}

CORE MISSION:
Explain this event's significance and likely impact.

When market context would be valuable, search for:
- Industry reactions to similar events
- Peer precedents
- Analyst commentary on this type of event

WORD COUNT GUIDANCE:
Target 400-800 words depending on event complexity.

ANALYSIS FRAMEWORK:
- Lead with the most newsworthy aspect [DOC:]
- Provide context and details [DOC:] 
- Search for industry perspective when relevant [1][2]
- Explain business impact
- What to watch next

CONTEXT:
Event Date: {context['filing_date']}
Event Type: {context.get('event_type', 'Material Event')}

FILING CONTENT:
{content}

Analyze this event with complete source attribution:"""
    
    def _build_s1_unified_prompt_enhanced(self, filing: Filing, content: str, context: Dict) -> str:
        """S-1 prompt with web search for IPO market context"""
        marking_instructions = self._build_data_marking_instructions()
        
        return f"""You are an IPO analyst evaluating {context['company_name']}'s public offering.

{marking_instructions}

CORE MISSION:
Help investors understand the opportunity, risks, and competitive position.

When market context would enrich analysis, search for:
- IPO market conditions and recent comparable offerings
- Industry growth forecasts
- Competitive landscape and peer valuations

WORD COUNT GUIDANCE:
Target 600-1000 words based on disclosure completeness.

CRITICAL AREAS:
1. **Investment Thesis** - Why go public now? [DOC: Business]
2. **Business Model** - Revenue model and economics [DOC:]
3. **Market Opportunity** - Validate TAM claims via search [1][2]
4. **Competitive Position** - Search for peer analysis [1]
5. **Risk Assessment** - Top material risks [DOC: Risk Factors]
6. **Valuation Context** - Search for comparable valuations [1]

CONTEXT:
Company: {context['company_name']}
Filing Date: {context['filing_date']}

FILING CONTENT:
{content}

Evaluate this IPO opportunity with complete source citations:"""
    
    def _build_generic_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Generic prompt for other filing types"""
        marking_instructions = self._build_data_marking_instructions()
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""You are a financial analyst examining this {filing_type_value} filing for {context['company_name']} ({context['ticker']}).

{marking_instructions}

Write an analysis that:
- Identifies key disclosures and their significance
- Uses specific data from filing with [DOC:] citations
- Searches for external context when it adds value [1][2]
- Maintains professional clarity

FILING CONTENT:
{content}"""
    
    async def _generate_text_with_search(self, prompt: str, max_tokens: int = 500) -> Tuple[str, List[Dict]]:
        """
        ✅ NEW: Generate text using OpenAI with web search support
        Returns: (text_content, references_list)
        """
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a professional financial analyst with expertise in SEC filings analysis. You have access to web search to enrich your analysis with industry context, peer comparisons, and analyst perspectives. Always cite your sources properly."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content.strip()
            
            # ✅ NEW: Extract annotations (web search results)
            annotations = getattr(response.choices[0].message, 'annotations', None) or []
            
            # ✅ NEW: Process citations into references
            references = self._process_citations(content, annotations)
            
            return content, references
            
        except Exception as e:
            logger.error(f"Error generating text with search: {e}")
            return "", []
    
    def _process_citations(self, content: str, annotations: List) -> List[Dict]:
        """
        ✅ NEW: Process OpenAI annotations into references list
        Returns: List of {id, title, url} for footnote-style citations
        """
        if not annotations:
            return []
        
        references = []
        url_to_id = {}
        
        for idx, annotation in enumerate(annotations, start=1):
            # Check if annotation has url_citation attribute
            if hasattr(annotation, 'url_citation'):
                url_citation = annotation.url_citation
                url = url_citation.url
                title = url_citation.title if hasattr(url_citation, 'title') else "Source"
                
                # Avoid duplicates
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
        """Generate compelling feed summary"""
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
            'has_surprise': any(word in unified_analysis.lower() for word in ['exceeded', 'missed', 'surprised']),
        }
        
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

        # Use regular generation for summary (no search needed)
        summary, _ = await self._generate_text_with_search(prompt, max_tokens=100)
        
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
        
        # Clean up markers
        summary = re.sub(r'\[DOC:[^\]]+\]', '', summary)
        summary = re.sub(r'\[\d+\]', '', summary)  # ✅ UPDATED: Also clean search citations
        summary = re.sub(r'\[CALC:[^\]]+\]', '', summary)
        summary = re.sub(r'\s+', ' ', summary).strip()
        
        return summary
    
    def _build_10k_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build summary prompt for 10-K"""
        ticker = self._get_safe_ticker(filing)
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s annual report.

Lead with the most newsworthy aspect. Create interest if there's contrast. Use specific numbers.

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the summary:"""
    
    def _build_10q_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build summary prompt for 10-Q"""
        ticker = self._get_safe_ticker(filing)
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s quarterly results.

Lead with beat/miss or biggest change. Include specific % or $ that tells the story.

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the summary:"""
    
    def _build_8k_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build summary prompt for 8-K"""
        ticker = self._get_safe_ticker(filing)
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s material event.

State what happened with specifics. Immediately explain why it matters.

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the summary:"""
    
    def _build_s1_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build summary prompt for S-1"""
        ticker = self._get_safe_ticker(filing)
        company_name = filing.company.name if filing.company else ticker
        identifier = company_name if ticker in ["UNKNOWN", "PRE-IPO"] or ticker.startswith("CIK") else ticker
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {identifier}'s IPO filing.

Capture what makes this IPO unique. Include valuation context or growth rate.

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the summary:"""
    
    def _build_generic_summary_prompt(self, filing: Filing, elements: Dict, analysis_excerpt: str) -> str:
        """Build generic summary prompt"""
        ticker = self._get_safe_ticker(filing)
        filing_type_value = self._get_safe_filing_type_value(filing.filing_type)
        
        return f"""Create a compelling 2-3 sentence summary (200-300 chars) for {ticker}'s {filing_type_value}.

Identify the most significant disclosure. Use specific data points.

Analysis excerpt:
{analysis_excerpt[:1000]}

Write the summary:"""
    
    def _extract_markup_data(self, text: str) -> Dict:
        """Extract smart markup metadata"""
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
        
        positive = re.findall(r'\+\[([^\]]+)\]', text)
        markup_data['positive'] = positive[:5]
        
        negative = re.findall(r'-\[([^\]]+)\]', text)
        markup_data['negative'] = negative[:5]
        
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
            r'\+\[[^\]]+\]',
            r'-\[[^\]]+\]'
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
        """
        Extract supplementary fields from unified analysis
        ❌ REMOVED: expectations_comparison logic
        """
        unified_text = unified_result['unified_analysis']
        ticker = self._get_safe_ticker(filing)
        
        # Extract enhanced tags
        filing.key_tags = self._generate_enhanced_tags(unified_result['markup_data'], unified_text, filing.filing_type, ticker)
        
        # Set legacy fields to None for backward compatibility
        filing.management_tone = None
        filing.tone_explanation = None
        filing.key_questions = []
        filing.financial_highlights = None
        filing.ai_summary = None
        
        # Extract event-specific fields for 8-K
        if filing.filing_type == FilingType.FORM_8K:
            filing.event_type = self._identify_8k_event_type(primary_content)
            filing.item_type = self._extract_8k_item_type(primary_content)
    
    def _generate_enhanced_tags(self, markup_data: Dict, unified_text: str, filing_type: Union[FilingType, str], ticker: str) -> List[str]:
        """Generate enhanced tags"""
        tags = []
        text_lower = unified_text.lower()
        
        # Industry tags
        industry_keywords = {
            'Technology': ['software', 'cloud', 'saas', 'platform', 'digital', 'ai'],
            'Healthcare': ['drug', 'clinical', 'fda', 'patient', 'therapeutic'],
            'Financial': ['banking', 'loan', 'deposit', 'interest rate', 'credit'],
            'Retail': ['store', 'e-commerce', 'consumer', 'brand'],
            'Energy': ['oil', 'gas', 'renewable', 'drilling'],
        }
        
        for industry, keywords in industry_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                tags.append(industry)
                break
        
        # Performance tags
        if markup_data['positive']:
            positive_text = ' '.join(markup_data['positive']).lower()
            if any(term in positive_text for term in ['beat', 'exceed', 'record', 'growth']):
                tags.append('Outperformance')
        
        if markup_data['negative']:
            negative_text = ' '.join(markup_data['negative']).lower()
            if any(term in negative_text for term in ['miss', 'below', 'decline']):
                tags.append('Underperformance')
        
        # Filing type tag
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
        """Extract Item number from 8-K"""
        item_pattern = r'Item\s+(\d+\.\d+)'
        match = re.search(item_pattern, content, re.IGNORECASE)
        return match.group(1) if match else None


# Initialize singleton
ai_processor = AIProcessor()