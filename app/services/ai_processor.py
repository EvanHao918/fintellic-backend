# app/services/ai_processor.py
"""
AI Processor Service - Enhanced Version with FMP Integration
Implements intelligent guidance approach with unified analysis
Focus on goals over rules, quality over format
ENHANCED: Smart content preprocessing and token management
ENHANCED: Filing type awareness for better prompts
UPDATED: Integrated FMP for analyst expectations
FIXED: Use period_end_date for analyst estimates matching
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


class AIProcessor:
    """
    Process filings using OpenAI to generate unified analysis with intelligent guidance
    Enhanced with smart content preprocessing and token management
    Updated with FMP integration for analyst expectations
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
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken"""
        try:
            return len(self.encoding.encode(text))
        except:
            # Fallback estimation
            return len(text) // 4
    
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
            'FORM_8K': ['item', 'event', 'agreement', 'announcement'],
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
        Process a filing using unified AI analysis
        
        Args:
            db: Database session
            filing: Filing to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update status
            filing.status = ProcessingStatus.AI_PROCESSING
            filing.processing_started_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Starting enhanced AI processing for {filing.company.ticker} {filing.filing_type.value}")
            
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
            
            if not primary_content or len(primary_content) < 100:
                raise Exception("Insufficient text content extracted")
            
            # Log content quality
            logger.info(f"Extracted content - Primary: {len(primary_content)} chars, Full: {len(full_text)} chars")
            
            # Get analyst expectations for 10-Q if enabled using FMP
            analyst_data = None
            if filing.filing_type == FilingType.FORM_10Q and settings.ENABLE_EXPECTATIONS_COMPARISON and settings.FMP_ENABLE:
                logger.info(f"[AI Processor] Fetching analyst expectations from FMP for {filing.company.ticker}")
                
                # FIXED: 使用 period_end_date 而不是 period_date
                target_date = None
                if filing.period_end_date:
                    target_date = filing.period_end_date.strftime('%Y-%m-%d')
                    logger.info(f"[AI Processor] Using period end date {target_date} to fetch expectations")
                elif filing.period_date:
                    # 向后兼容：如果没有 period_end_date，尝试 period_date
                    target_date = filing.period_date.strftime('%Y-%m-%d')
                    logger.info(f"[AI Processor] Using period date {target_date} to fetch expectations (fallback)")
                elif filing.filing_date:
                    # 最后的备选：使用 filing_date
                    target_date = filing.filing_date.strftime('%Y-%m-%d')
                    logger.info(f"[AI Processor] Using filing date {target_date} to fetch expectations (last resort)")
                
                # 获取对应期间的预期数据
                analyst_data = await fmp_service.get_analyst_estimates(
                    filing.company.ticker,
                    target_date=target_date
                )
                
                if analyst_data:
                    logger.info(f"[AI Processor] Retrieved analyst expectations from FMP for {filing.company.ticker}")
                    logger.info(f"[AI Processor] Expectations for period: {analyst_data.get('period')}")
                    
                    # 验证日期匹配质量
                    if target_date and analyst_data.get('period'):
                        target_dt = datetime.strptime(target_date, '%Y-%m-%d')
                        estimate_dt = datetime.strptime(analyst_data['period'], '%Y-%m-%d')
                        diff_days = abs((target_dt - estimate_dt).days)
                        
                        if diff_days <= 10:
                            logger.info(f"[AI Processor] Excellent match: {diff_days} days difference")
                        elif diff_days <= 30:
                            logger.info(f"[AI Processor] Good match: {diff_days} days difference")
                        elif diff_days <= 45:
                            logger.warning(f"[AI Processor] Acceptable match: {diff_days} days difference")
                        else:
                            logger.warning(f"[AI Processor] Poor match: {diff_days} days difference - may affect accuracy")
                else:
                    logger.info(f"[AI Processor] No analyst expectations available from FMP for {filing.company.ticker}")
            
            # Generate unified analysis with intelligent retry
            unified_result = await self._generate_unified_analysis_with_retry(
                filing, primary_content, full_text, analyst_data
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.analysis_version = "v4"  # Enhanced version
            
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
            
            # Validate word count with flexibility
            word_count = len(unified_result['unified_analysis'].split())
            target_min = int(settings.UNIFIED_ANALYSIS_MIN_WORDS * 0.9)  # Allow 10% flexibility
            
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
                logger.warning(f"Word count {word_count} below target, enhancing content for retry...")
                # Next iteration will use more content
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
        content = self._smart_truncate_content(content, available_tokens, filing_type)
        
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
        
        # Generate feed summary from unified analysis
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
    
    def _build_10k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build reformed prompt for 10-K filings - intelligent guidance approach"""
        return f"""You are a seasoned equity analyst writing for retail investors who want professional insights in accessible language.

CORE MISSION: 
Create a comprehensive 1000-1200 word analysis of this annual report that helps readers understand {filing.company.name}'s ({filing.company.ticker}) year in review and future prospects.

CONTENT CONTEXT:
This filing contains key sections including business overview, risk factors, management discussion & analysis (MD&A), and financial statements. Focus on the most material information provided.

KEY PRINCIPLES:
1. **Data Integrity**: Every number must come from THIS filing - trace metrics to their source
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

UNIFIED STYLE:
Combine structured analysis with compelling narrative - let data tell the story within clear sections.

TARGET READER: Sophisticated retail investors - smart individuals who aren't finance experts but understand business fundamentals.

CONTEXT:
Fiscal Year: {context.get('fiscal_year', 'FY2024')}
Period End: {context.get('period_end_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Now, tell the story of {filing.company.ticker}'s year and what it means for investors."""
    
    def _build_10q_unified_prompt(self, filing: Filing, content: str, context: Dict, analyst_data: Optional[Dict] = None) -> str:
        """Build reformed prompt for 10-Q filings - intelligent guidance approach"""
        analyst_context = ""
        if analyst_data:
            rev_est = analyst_data.get('revenue_estimate', {})
            eps_est = analyst_data.get('eps_estimate', {})
            
            if rev_est.get('value') or eps_est.get('value'):
                analyst_context = "\nANALYST EXPECTATIONS:"
                
                if rev_est.get('value'):
                    analyst_context += f"\nRevenue Consensus: ${rev_est.get('value')}B"
                    if rev_est.get('analysts'):
                        analyst_context += f" ({rev_est.get('analysts')} analysts)"
                        
                if eps_est.get('value'):
                    analyst_context += f"\nEPS Consensus: ${eps_est.get('value')}"
                    if eps_est.get('analysts'):
                        analyst_context += f" ({eps_est.get('analysts')} analysts)"
                
                analyst_context += "\nCompare these expectations with actual results to identify beats or misses\n"
        
        return f"""You are a professional equity analyst writing for retail investors seeking clear quarterly insights.

CORE MISSION:
Write a comprehensive 800-1000 word analysis of {filing.company.name}'s ({filing.company.ticker}) quarterly results that answers: What happened? Why does it matter? What's next?

CONTENT CONTEXT:
This quarterly filing includes financial statements and management's discussion of the quarter's performance. Focus on the key drivers and changes.

KEY PRINCIPLES:
1. **Data Integrity & Comparison**: 
   - Use actual performance numbers from THIS filing
   - When analyst consensus is provided, compare actuals vs. expectations
   - Always clearly distinguish between reported results and analyst estimates
2. **Clear Story Arc**: Performance → Drivers → Implications → Outlook
3. **Professional Terms**: Keep Revenue, EBITDA, etc. but explain their significance
4. **Visual Structure**: Use ## for major sections and --- for transitions
5. **Smart Emphasis**: 
   - Use *asterisks* for key metrics from the filing
   - Use **bold** for important concepts and strategic points
   - Use +[positive trends] for beats or positive surprises
   - Use -[negative trends] for misses or challenges

ANALYSIS APPROACH:
- Open with the quarter's defining moment or metric
- Present the quarter's story within a clear analytical framework
- State actual results clearly, then compare with consensus when available
- Explain both what happened and why it matters through cause-effect narrative
- Connect the numbers to business realities and the bigger picture
- Note significant surprises and their implications
- Close with concrete takeaways for investors

UNIFIED STYLE:
Balance structured sections with engaging narrative flow - each section should connect naturally to the next.

TARGET READER: Sophisticated retail investors - smart individuals who want to understand the investment implications quickly.

CONTEXT:
Quarter: {context.get('fiscal_quarter', 'Q3 2024')}
Current Date: {datetime.now().strftime('%B %d, %Y')}
{analyst_context}

FILING CONTENT:
{content}

Analyze this quarter's performance and tell investors what they need to know."""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build reformed prompt for 8-K filings - intelligent guidance approach"""
        return f"""You are a financial journalist analyzing a material event for {filing.company.name} ({filing.company.ticker}).

CORE MISSION:
In 600-800 words, explain this event's significance and likely impact on the company and its investors.

CONTENT CONTEXT:
This 8-K filing reports a material event or change. The content includes specific Item disclosures that describe what happened.

KEY PRINCIPLES:
1. **Event Focus**: What happened and why it matters - get to the point quickly
2. **Impact Analysis**: Immediate and longer-term implications
3. **Data Grounding**: Support your analysis with specific details from the filing
4. **News Style**: Direct, factual, implications-focused writing
5. **Targeted Emphasis**: Use *asterisks* for key facts and **bold** for critical implications

ANALYSIS FRAMEWORK:
- Lead with what happened and its materiality (news hook)
- Explain the business/financial impact through clear narrative
- Consider the strategic implications within company context
- Project likely market reaction and what to watch
- Maintain analytical depth while keeping news-style urgency

UNIFIED STYLE:
Even in shorter format, maintain narrative coherence - tell the complete event story.

TARGET READER: Sophisticated retail investors who already know the company but need to understand this specific event.

CONTEXT:
Event Date: {context.get('filing_date', '')}
Item Type: {context.get('event_type', 'Material Event')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Analyze this event and its implications for investors."""
    
    def _build_s1_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build reformed prompt for S-1 filings - intelligent guidance approach"""
        return f"""You are an IPO analyst evaluating {filing.company.name}'s public offering for potential investors.

CORE MISSION:
Create a comprehensive 800-1000 word analysis that helps investors understand the investment opportunity and risks.

CONTENT CONTEXT:
This S-1 registration statement includes business overview, risk factors, use of proceeds, and financial information for a company going public.

KEY PRINCIPLES:
1. **Investment Thesis**: What's the opportunity and why should investors care?
2. **Business Reality**: Use specific data from the S-1 to support your analysis
3. **Balanced View**: Both opportunity and risk deserve thorough attention
4. **IPO Specifics**: Valuation indicators, use of proceeds, growth trajectory
5. **Clear Emphasis**: Use *asterisks* for key metrics and **bold** for critical insights

CRITICAL ELEMENTS TO ADDRESS:
- Business model and competitive position (tell their story)
- Financial trajectory and unit economics (growth narrative)
- Cash burn rate and runway (sustainability story)
- Key risks from Risk Factors section (balanced reality)
- Management and governance insights (leadership narrative)

UNIFIED STYLE:
Present the investment opportunity as a coherent story backed by rigorous analysis.

TARGET READER: Sophisticated retail investors considering an IPO investment.

CONTEXT:
Filing Date: {context.get('filing_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Evaluate this IPO opportunity with clear analysis and concrete insights for potential investors."""
    
    def _build_generic_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build generic prompt for other filing types"""
        return f"""You are a financial analyst examining this {filing.filing_type.value} filing for {filing.company.name} ({filing.company.ticker}).

Write a 600-800 word analysis that:
1. Identifies the key disclosures and their significance
2. Explains the implications for investors
3. Uses specific data from the filing to support your points
4. Maintains professional clarity throughout

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
        
        if filing.filing_type == FilingType.FORM_8K and filing.event_type:
            context['event_type'] = filing.event_type
            
        return context
    
    async def _generate_feed_summary_from_unified(self, unified_analysis: str, filing_type: str, filing: Filing) -> str:
        """Generate a one-line feed summary from unified analysis"""
        key_numbers = re.findall(r'\*([^*]+)\*', unified_analysis)[:5]
        key_concepts = re.findall(r'\*\*([^*]+)\*\*', unified_analysis)[:3]
        
        prompt = f"""Create a single compelling sentence (max 100 characters) that captures the essence of this {filing.company.ticker} {filing_type} filing.

Key elements from analysis: {', '.join(key_numbers[:3]) if key_numbers else 'No specific numbers found'}

Requirements:
1. Start with ticker: "{filing.company.ticker}:"
2. Include one specific number from the analysis
3. Maximum 100 characters total
4. Make it newsworthy and specific

Analysis excerpt:
{unified_analysis[:1500]}

Write the summary:"""

        summary = await self._generate_text(prompt, max_tokens=50)
        
        # Ensure ticker is included
        if filing.company.ticker not in summary:
            summary = f"{filing.company.ticker}: {summary}"
            
        # Ensure length limit
        if len(summary) > 100:
            summary = summary[:97] + "..."
            
        return summary
    
    def _extract_markup_data(self, text: str) -> Dict:
        """Extract smart markup metadata for frontend rendering"""
        markup_data = {
            'numbers': [],
            'concepts': [],
            'positive': [],
            'negative': [],
            'sections': []
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
        
        # Generate questions based on unified analysis
        filing.key_questions = await self._generate_questions_from_unified(
            filing.company.name, filing.filing_type.value, unified_text
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
        
        if 'item 1.01' in content_lower or 'entry into' in content_lower:
            return "Material Agreement"
        elif 'item 2.02' in content_lower or 'results of operations' in content_lower:
            return "Earnings Release"
        elif 'item 5.02' in content_lower or ('departure' in content_lower and 'officer' in content_lower):
            return "Executive Change"
        elif 'item 7.01' in content_lower or 'regulation fd' in content_lower:
            return "Regulation FD Disclosure"
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
                    {"role": "system", "content": "You are a professional financial analyst with expertise in SEC filings analysis. Write in clear, professional English suitable for sophisticated retail investors."},
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