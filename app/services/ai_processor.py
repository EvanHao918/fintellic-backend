# app/services/ai_processor.py
"""
AI Processor Service - Reformed Version
Implements intelligent guidance approach with unified analysis
Focus on goals over rules, quality over format
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
from pathlib import Path
import yfinance as yf
import time
from random import uniform
import requests
from bs4 import BeautifulSoup
import asyncio

from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.filing import Filing, ProcessingStatus, ManagementTone, FilingType
from app.core.config import settings
from app.services.text_extractor import text_extractor
from app.core.cache import cache

logger = logging.getLogger(__name__)

# Configure yfinance to use browser-like headers
_headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class AIProcessor:
    """
    Process filings using OpenAI to generate unified analysis with intelligent guidance
    """
    
    def __init__(self):
        self.model = settings.AI_MODEL
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        
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
            
            logger.info(f"Starting unified AI processing for {filing.company.ticker} {filing.filing_type.value}")
            
            # Get filing directory
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            
            # Extract text
            sections = text_extractor.extract_from_filing(filing_dir)
            
            if 'error' in sections:
                raise Exception(f"Text extraction failed: {sections['error']}")
            
            primary_content = sections.get('primary_content', '')
            full_text = sections.get('full_text', '')
            
            if not primary_content or len(primary_content) < 100:
                raise Exception("Insufficient text content extracted")
            
            # Get analyst expectations for 10-Q if enabled
            analyst_data = None
            if filing.filing_type == FilingType.FORM_10Q and settings.ENABLE_EXPECTATIONS_COMPARISON:
                logger.info(f"[AI Processor] Fetching analyst expectations for {filing.company.ticker}")
                analyst_data = await self._fetch_analyst_expectations(filing.company.ticker)
                
                if analyst_data:
                    logger.info(f"[AI Processor] Retrieved analyst expectations for {filing.company.ticker}")
                else:
                    logger.info(f"[AI Processor] No analyst expectations available for {filing.company.ticker}")
            
            # Generate unified analysis with intelligent retry
            unified_result = await self._generate_unified_analysis_with_retry(
                filing, primary_content, full_text, analyst_data
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.analysis_version = "v3"  # Reformed version
            
            if analyst_data:
                filing.analyst_expectations = analyst_data
            
            # Extract supplementary fields from unified analysis
            await self._extract_supplementary_fields(filing, unified_result, primary_content, full_text)
            
            # Set status
            filing.status = ProcessingStatus.COMPLETED
            filing.processing_completed_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"✅ Unified AI processing completed for {filing.accession_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error in unified AI processing: {e}")
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
        Generate unified analysis with intelligent retry logic
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            # Generate analysis
            unified_result = await self._generate_unified_analysis(
                filing, primary_content, full_text, analyst_data
            )
            
            # Validate word count with flexibility
            word_count = len(unified_result['unified_analysis'].split())
            target_min = int(settings.UNIFIED_ANALYSIS_MIN_WORDS * 0.9)  # Allow 10% flexibility
            
            # Check for template numbers
            if self._contains_template_numbers(unified_result['unified_analysis']):
                logger.warning(f"Template numbers detected, retrying... (attempt {attempt + 1})")
                continue
            
            if word_count >= target_min:
                logger.info(f"Generated {word_count} words, within acceptable range")
                break
            elif attempt < max_retries - 1:
                logger.warning(f"Word count {word_count} below target, enhancing prompt for retry...")
                # Will enhance prompt in next iteration
                continue
        
        # Final optimization
        unified_result['unified_analysis'] = self._optimize_markup_density(
            unified_result['unified_analysis']
        )
        
        return unified_result
    
    def _contains_template_numbers(self, text: str) -> bool:
        """Check if analysis contains suspicious template numbers"""
        template_patterns = [
            r'\$5\.2B',
            r'exceeded.*by.*6%',
            r'\$4\.9B'
        ]
        
        for pattern in template_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    async def _fetch_analyst_expectations(self, ticker: str) -> Optional[Dict]:
        """
        Fetch analyst expectations (revenue and EPS estimates)
        """
        if not settings.ENABLE_EXPECTATIONS_COMPARISON:
            logger.info(f"[AI Processor] Expectations comparison disabled")
            return None
            
        try:
            # Check cache first
            cache_key = f"analyst_expectations:{ticker}"
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"[YahooFinance] Cache hit for {ticker}")
                return json.loads(cached_data)
            
            logger.info(f"[YahooFinance] Fetching analyst expectations for {ticker}")
            
            # Add random delay to avoid being detected as bot
            await asyncio.sleep(uniform(1, 2))
            
            # Method 1: Try web scraping analyst page
            result = await self._fetch_analyst_estimates_web(ticker)
            if result:
                cache.set(cache_key, json.dumps(result), ttl=settings.EXPECTATIONS_CACHE_TTL)
                logger.info(f"[YahooFinance] Successfully fetched analyst estimates via web for {ticker}")
                return result
                
            # Method 2: Try yfinance with safer approach
            result = await self._fetch_analyst_estimates_yfinance(ticker)
            if result:
                cache.set(cache_key, json.dumps(result), ttl=settings.EXPECTATIONS_CACHE_TTL)
                logger.info(f"[YahooFinance] Successfully fetched analyst estimates via yfinance for {ticker}")
                return result
            
            logger.warning(f"[YahooFinance] No analyst estimates available for {ticker}")
            return None
            
        except Exception as e:
            logger.error(f"[YahooFinance] Error fetching expectations for {ticker}: {str(e)}")
            return None
    
    async def _fetch_analyst_estimates_web(self, ticker: str) -> Optional[Dict]:
        """
        Fetch analyst estimates by scraping Yahoo Finance analysis page
        """
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}/analysis"
            
            response = requests.get(url, headers=_headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result = {
                'revenue_estimate': {},
                'eps_estimate': {},
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'web_analysis_page'
            }
            
            # Look for earnings estimate tables
            tables = soup.find_all('table')
            
            for table in tables:
                header_text = table.get_text()
                
                if 'Revenue Estimate' in header_text:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text().strip()
                            if 'Avg. Estimate' in label:
                                value_text = cells[1].get_text().strip()
                                result['revenue_estimate']['value'] = self._parse_financial_value(value_text)
                            elif 'No. of Analysts' in label:
                                result['revenue_estimate']['analysts'] = int(cells[1].get_text().strip())
                                
                elif 'Earnings Estimate' in header_text:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text().strip()
                            if 'Avg. Estimate' in label:
                                value_text = cells[1].get_text().strip()
                                result['eps_estimate']['value'] = float(value_text)
                            elif 'No. of Analysts' in label:
                                result['eps_estimate']['analysts'] = int(cells[1].get_text().strip())
            
            if (result['revenue_estimate'].get('value') or 
                result['eps_estimate'].get('value')):
                return result
                
            return None
            
        except Exception as e:
            logger.debug(f"[YahooFinance] Web scraping analysis page failed for {ticker}: {str(e)}")
            return None
    
    async def _fetch_analyst_estimates_yfinance(self, ticker: str) -> Optional[Dict]:
        """
        Fetch analyst estimates using yfinance with custom session
        """
        try:
            session = requests.Session()
            session.headers.update(_headers)
            
            await asyncio.sleep(1)
            
            stock = yf.Ticker(ticker, session=session)
            
            result = {
                'revenue_estimate': {},
                'eps_estimate': {},
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'data_source': 'yfinance_custom_session'
            }
            
            try:
                analysis = stock.analysis
                if analysis is not None and not analysis.empty:
                    if 'Revenue Estimate' in analysis.index:
                        revenue_row = analysis.loc['Revenue Estimate']
                        if 'Current Qtr' in revenue_row:
                            result['revenue_estimate']['value'] = revenue_row['Current Qtr'] / 1e9
                            
                    if 'Earnings Estimate' in analysis.index:
                        eps_row = analysis.loc['Earnings Estimate']
                        if 'Current Qtr' in eps_row:
                            result['eps_estimate']['value'] = eps_row['Current Qtr']
            except:
                pass
            
            try:
                info = stock.info
                if info:
                    if 'revenueEstimates' in info:
                        result['revenue_estimate']['value'] = info['revenueEstimates'].get('avg', {}).get('raw', 0) / 1e9
                    if 'epsEstimates' in info:
                        result['eps_estimate']['value'] = info['epsEstimates'].get('avg', {}).get('raw', 0)
            except:
                pass
            
            if (result['revenue_estimate'].get('value') or 
                result['eps_estimate'].get('value')):
                return result
                
            return None
            
        except Exception as e:
            logger.debug(f"[YahooFinance] yfinance method failed for {ticker}: {str(e)}")
            return None
    
    def _parse_financial_value(self, text: str) -> float:
        """
        Parse financial values like '89.5B' or '1.23T' to float
        """
        try:
            text = text.strip().upper()
            if 'T' in text:
                return float(text.replace('T', '').replace(',', '')) * 1000
            elif 'B' in text:
                return float(text.replace('B', '').replace(',', ''))
            elif 'M' in text:
                return float(text.replace('M', '').replace(',', '')) / 1000
            else:
                return float(text.replace(',', ''))
        except:
            return 0.0
    
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
        # Use full content without truncation
        content = full_text
        
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
Create a 1000-1200 word analysis of this annual report that helps readers understand {filing.company.name}'s ({filing.company.ticker}) year in review and future prospects.

KEY PRINCIPLES:
1. **Data Integrity**: Every number must come from THIS filing - trace metrics to their source
2. **Clear Narrative**: Tell the story of the year - what worked, what didn't, what's changing
3. **Professional Clarity**: Keep financial terms but explain their business significance
4. **Natural Structure**: Use ## headers and --- breaks to guide readers through your analysis
5. **Appropriate Emphasis**: Highlight truly important metrics with *markup*, not everything

QUALITY GUIDANCE:
- Start with your most compelling finding from the annual results
- Balance between financial performance and strategic developments
- Compare actual results to guidance when available
- Identify 2-3 key risks or opportunities from the filing
- Make the implications clear for investors

Remember: You're writing for smart people who aren't finance experts. Be thorough but accessible.

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
                analyst_context = "\nANALYST CONTEXT:"
                
                if rev_est.get('value'):
                    analyst_context += f"\nRevenue Consensus: ${rev_est.get('value')}B"
                    if rev_est.get('analysts'):
                        analyst_context += f" ({rev_est.get('analysts')} analysts)"
                        
                if eps_est.get('value'):
                    analyst_context += f"\nEPS Consensus: ${eps_est.get('value')}"
                    if eps_est.get('analysts'):
                        analyst_context += f" ({eps_est.get('analysts')} analysts)"
                
                analyst_context += "\nIncorporate beat/miss analysis naturally if significant\n"
        
        return f"""You are a professional equity analyst writing for retail investors seeking clear quarterly insights.

CORE MISSION:
Write an 800-1000 word analysis of {filing.company.name}'s ({filing.company.ticker}) quarterly results that answers: What happened? Why does it matter? What's next?

KEY PRINCIPLES:
1. **Real Data Only**: Use numbers from THIS filing - no templates or examples
2. **Clear Story Arc**: Performance → Drivers → Implications → Outlook
3. **Professional Terms**: Keep Revenue, EBITDA, etc. but explain their significance
4. **Visual Structure**: Use ## for major sections and --- for transitions
5. **Smart Emphasis**: Mark key metrics with *asterisks* and important concepts with **bold**

ANALYSIS APPROACH:
- Open with the quarter's defining moment or metric
- Explain both what happened and why
- Connect the numbers to business realities
- If expectations data exists, note significant surprises
- Close with concrete implications for investors

TARGET READER: Someone smart who wants to understand the investment implications quickly.

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

KEY PRINCIPLES:
1. **Event Focus**: What happened and why it matters - get to the point quickly
2. **Impact Analysis**: Immediate and longer-term implications
3. **Data Grounding**: Support your analysis with filing specifics
4. **News Style**: Direct, factual, implications-focused writing

ANALYSIS FRAMEWORK:
- Lead with what happened and its materiality
- Explain the business/financial impact
- Consider the strategic implications
- Project likely market reaction and what to watch

No need for extensive background - readers know the company. Focus on this event.

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
Create an 800-1000 word analysis that helps investors understand the investment opportunity and risks.

KEY PRINCIPLES:
1. **Investment Thesis**: What's the opportunity and why should investors care?
2. **Business Reality**: Use S-1 data to show, not just tell
3. **Balanced View**: Both opportunity and risk deserve attention
4. **IPO Specifics**: Valuation indicators, use of proceeds, growth trajectory

CRITICAL ELEMENTS TO ADDRESS:
- Business model and competitive position (from filing)
- Financial trajectory and unit economics
- Cash burn rate and runway
- Key risks from Risk Factors section
- Management and governance insights

Write for someone considering an investment - what do they need to know?

CONTEXT:
Filing Date: {context.get('filing_date', '')}
Current Date: {datetime.now().strftime('%B %d, %Y')}

FILING CONTENT:
{content}

Evaluate this IPO opportunity with clear analysis and concrete insights."""
    
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