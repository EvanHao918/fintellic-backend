# app/services/ai_processor.py
"""
AI Processor Service - Unified Analysis Version
Implements single-pass unified analysis with smart markup
Optimized for content quality and API efficiency
"""
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
import logging
from pathlib import Path
import aiohttp

from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.filing import Filing, ProcessingStatus, ManagementTone, FilingType
from app.core.config import settings
from app.services.text_extractor import text_extractor

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class AIProcessor:
    """
    Process filings using OpenAI to generate unified analysis with smart markup
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
                analyst_data = await self._fetch_analyst_expectations(filing.company.ticker)
            
            # Generate unified analysis
            unified_result = await self._generate_unified_analysis(
                filing, primary_content, full_text, analyst_data
            )
            
            # Store unified analysis fields
            filing.unified_analysis = unified_result['unified_analysis']
            filing.unified_feed_summary = unified_result['feed_summary']
            filing.smart_markup_data = unified_result['markup_data']
            filing.analysis_version = "v2"
            
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
    
    async def _generate_unified_analysis(
        self, 
        filing: Filing, 
        primary_content: str, 
        full_text: str,
        analyst_data: Optional[Dict] = None
    ) -> Dict:
        """
        Generate unified analysis with smart markup
        """
        content = self._prepare_content(primary_content)
        
        # Build filing-specific context
        filing_context = self._build_filing_context(filing, analyst_data)
        
        # Generate unified analysis with appropriate prompt
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
            unified_analysis, filing.filing_type.value
        )
        
        # Extract smart markup data
        markup_data = self._extract_markup_data(unified_analysis)
        
        return {
            'unified_analysis': unified_analysis,
            'feed_summary': feed_summary,
            'markup_data': markup_data
        }
    
    def _build_10k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build unified prompt for 10-K filings"""
        return f"""You are a professional equity analyst writing for sophisticated retail investors. Create a compelling annual report analysis for {filing.company.name} ({filing.company.ticker}).

STRICT REQUIREMENTS:
1. Write exactly 800-1200 words
2. Professional investment report style - no AI markers like "First, Second, Lastly"
3. Open with a strong hook - a surprising insight or contrarian observation
4. Each paragraph 50-80 words max, with clear logical flow
5. Use smart markup for emphasis (see markup rules below)

SMART MARKUP RULES:
- Key numbers: *37%* or *$5.2B*
- Important concepts: **transformation** or **market leadership**
- Positive trends: +[revenue up 15%]
- Negative trends: -[margins compressed 120bps]
- Critical insights: [!This marks a strategic inflection point]

CONTENT FOCUS for 10-K:
1. Annual performance trajectory and inflection points
2. Strategic positioning changes during the year
3. Capital allocation effectiveness
4. Competitive dynamics evolution
5. Management execution track record
6. Forward-looking strategic priorities
7. Key risks that materialized or emerged

CONTEXT:
Fiscal Year: {context.get('fiscal_year', 'FY2024')}
Period End: {context.get('period_end_date', '')}

FILING CONTENT:
{content}

Write a narrative that tells the investment story, not a mechanical summary. Focus on what changed, why it matters, and what to watch going forward."""
    
    def _build_10q_unified_prompt(self, filing: Filing, content: str, context: Dict, analyst_data: Optional[Dict] = None) -> str:
        """Build unified prompt for 10-Q filings"""
        analyst_context = ""
        if analyst_data:
            analyst_context = f"""
ANALYST EXPECTATIONS:
Revenue Estimate: ${analyst_data.get('revenue_estimate', {}).get('value', 'N/A')}
EPS Estimate: ${analyst_data.get('eps_estimate', {}).get('value', 'N/A')}
Number of Analysts: {analyst_data.get('revenue_estimate', {}).get('analysts', 'N/A')}
"""
        
        return f"""You are a professional equity analyst writing for sophisticated retail investors. Create a compelling quarterly earnings analysis for {filing.company.name} ({filing.company.ticker}).

STRICT REQUIREMENTS:
1. Write exactly 800-1200 words
2. Professional investment report style - punchy, insightful, no fluff
3. Open with the most important takeaway - performance vs expectations if available
4. Each paragraph 50-80 words max, crisp and impactful
5. Use smart markup strategically (see rules below)

SMART MARKUP RULES:
- Key metrics: *12%* or *$1.3B*
- Critical concepts: **margin expansion** or **guidance raise**
- Beats/positive: +[EPS beat by $0.05]
- Misses/negative: -[revenue miss by 2%]
- Key insights: [!This suggests sustainable momentum]

CONTENT FOCUS for 10-Q:
1. Performance vs expectations (if analyst data provided)
2. Sequential and year-over-year momentum
3. Margin trajectory and operational leverage
4. Guidance changes and management confidence
5. Business mix evolution
6. Cash generation and capital deployment
7. Near-term catalysts and concerns

CONTEXT:
Quarter: {context.get('fiscal_quarter', 'Q3 2024')}
{analyst_context}

FILING CONTENT:
{content}

Tell the quarterly story - what drove results, what surprised, and what it means for the investment thesis."""
    
    def _build_8k_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build unified prompt for 8-K filings"""
        return f"""You are a financial journalist writing a market-moving event analysis for {filing.company.name} ({filing.company.ticker}).

STRICT REQUIREMENTS:
1. Write exactly 600-800 words
2. News article style - direct, factual, implications-focused
3. Lead with what happened and why it matters
4. Short paragraphs, 40-60 words each
5. Use smart markup sparingly for emphasis

SMART MARKUP RULES:
- Key facts: *CEO departure* or *$2B acquisition*
- Material changes: **strategic pivot**
- Positive implications: +[accretive to earnings]
- Negative implications: -[integration risk]
- Critical insight: [!This changes the growth trajectory]

CONTENT FOCUS for 8-K:
1. What exactly was announced/disclosed
2. Immediate implications for operations
3. Financial impact assessment
4. Strategic rationale or context
5. Implementation timeline
6. Key risks or uncertainties
7. Market precedents or comparisons

EVENT TYPE: {context.get('event_type', 'Material Event')}

FILING CONTENT:
{content}

Focus on why this event matters to investors and what they should monitor going forward."""
    
    def _build_s1_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build unified prompt for S-1 filings"""
        return f"""You are an IPO analyst writing for potential investors in {filing.company.name}'s public offering.

STRICT REQUIREMENTS:
1. Write exactly 800-1000 words
2. IPO research preview style - balanced but engaging
3. Open with the investment thesis in one compelling sentence
4. Structured narrative with 60-80 word paragraphs
5. Use smart markup to highlight key data

SMART MARKUP RULES:
- Key metrics: *125% revenue growth* or *$500M addressable market*
- Differentiators: **proprietary technology** or **first-mover advantage**
- Strengths: +[85% gross margins]
- Risks: -[cash burn of $10M/month]
- Critical insights: [!Path to profitability unclear]

CONTENT FOCUS for S-1:
1. Business model clarity and unit economics
2. Market opportunity size and capture strategy
3. Competitive differentiation and moat
4. Growth trajectory and scalability
5. Path to profitability timeline
6. Use of proceeds priorities
7. Key risk factors that could derail the story

FILING CONTENT:
{content}

Write an analysis that helps investors understand if this IPO offers compelling value at likely valuations."""
    
    def _build_generic_unified_prompt(self, filing: Filing, content: str, context: Dict) -> str:
        """Build generic unified prompt for other filing types"""
        return f"""You are a financial analyst creating a summary of this {filing.filing_type.value} filing for {filing.company.name} ({filing.company.ticker}).

Write a professional analysis (600-800 words) that:
1. Explains what was disclosed and why it matters
2. Uses clear paragraphs of 50-80 words
3. Includes relevant financial metrics with *markup*
4. Highlights key insights with [!insight markers]

Focus on material information that impacts investment decisions.

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
        
        # Add event type for 8-K
        if filing.filing_type == FilingType.FORM_8K and filing.event_type:
            context['event_type'] = filing.event_type
            
        return context
    
    async def _generate_feed_summary_from_unified(self, unified_analysis: str, filing_type: str) -> str:
        """Generate a one-line feed summary from unified analysis"""
        prompt = f"""Based on this {filing_type} analysis, create a single compelling sentence (max 100 characters) that captures the most important takeaway:

{unified_analysis[:1000]}

Requirements:
- Must be under 100 characters
- Focus on the single most important fact or trend
- Use active voice
- Be specific with numbers when relevant
- No markup or special characters"""

        return await self._generate_text(prompt, max_tokens=settings.AI_FEED_SUMMARY_MAX_TOKENS)
    
    def _extract_markup_data(self, text: str) -> Dict:
        """Extract smart markup metadata for frontend rendering"""
        markup_data = {
            'numbers': [],
            'concepts': [],
            'positive': [],
            'negative': [],
            'insights': []
        }
        
        # Extract key numbers: *value*
        numbers = re.findall(r'\*([^*]+)\*', text)
        markup_data['numbers'] = numbers[:10]  # Limit to 10
        
        # Extract concepts: **concept**
        concepts = re.findall(r'\*\*([^*]+)\*\*', text)
        markup_data['concepts'] = concepts[:8]
        
        # Extract positive trends: +[text]
        positive = re.findall(r'\+\[([^\]]+)\]', text)
        markup_data['positive'] = positive[:5]
        
        # Extract negative trends: -[text]
        negative = re.findall(r'-\[([^\]]+)\]', text)
        markup_data['negative'] = negative[:5]
        
        # Extract insights: [!text]
        insights = re.findall(r'\[!([^\]]+)\]', text)
        markup_data['insights'] = insights[:3]
        
        return markup_data
    
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
        
        # Set ai_summary to first 2-3 paragraphs for backward compatibility
        paragraphs = unified_text.split('\n\n')
        filing.ai_summary = '\n\n'.join(paragraphs[:3])
        
        # Extract key type-specific fields if needed
        if filing.filing_type == FilingType.FORM_10K:
            filing.financial_highlights = await self._extract_financial_highlights(unified_text)
        elif filing.filing_type == FilingType.FORM_10Q:
            filing.core_metrics = await self._extract_financial_highlights(unified_text)
            if unified_result.get('analyst_data'):
                filing.expectations_comparison = await self._extract_expectations_narrative(unified_text, unified_result['analyst_data'])
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

Format:
TONE: [classification]
EXPLANATION: [2-3 sentence explanation]"""

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
Q: [Question]
A: [Brief answer, 2-3 sentences]"""

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
            tags.append('Challenges')
        
        # Content-based tags
        if any('margin' in concept.lower() for concept in markup_data['concepts']):
            tags.append('Margins')
        if 'guidance' in text_lower:
            tags.append('Guidance Update')
        if any(word in text_lower for word in ['dividend', 'buyback', 'repurchase']):
            tags.append('Capital Return')
        if any(word in text_lower for word in ['acquisition', 'merger', 'm&a']):
            tags.append('M&A')
        
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
        prompt = f"""Extract key financial metrics mentioned in this analysis and create a brief financial highlights summary.

Analysis:
{unified_text[:2000]}

Create a 100-150 word summary focusing on:
- Revenue figures and growth
- Profitability metrics
- Margin performance
- Cash position
- Any other key financial metrics mentioned

Write in narrative form, not bullet points."""

        return await self._generate_text(prompt, max_tokens=200)
    
    async def _extract_expectations_narrative(self, unified_text: str, analyst_data: Dict) -> str:
        """Create expectations comparison narrative"""
        prompt = f"""Based on this analysis and analyst expectations data, create a brief comparison narrative.

Analyst Expectations:
Revenue Estimate: ${analyst_data.get('revenue_estimate', {}).get('value', 'N/A')}
EPS Estimate: ${analyst_data.get('eps_estimate', {}).get('value', 'N/A')}

Analysis excerpt:
{unified_text[:1000]}

Write 100-150 words comparing actual results to expectations, if mentioned."""

        return await self._generate_text(prompt, max_tokens=200)
    
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
    
    async def _fetch_analyst_expectations(self, ticker: str) -> Optional[Dict]:
        """Fetch analyst expectations from Yahoo Finance API"""
        if not settings.YAHOO_FINANCE_API_KEY:
            return None
            
        try:
            # TODO: Implement actual Yahoo Finance API call
            # This is a placeholder structure
            url = f"https://api.yahoofinance.com/v1/finance/quote/{ticker}/analysts"
            headers = {"X-API-KEY": settings.YAHOO_FINANCE_API_KEY}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Parse and return relevant expectations
                        return {
                            'revenue_estimate': {
                                'value': data.get('revenue', {}).get('avg'),
                                'analysts': data.get('revenue', {}).get('numberOfAnalysts')
                            },
                            'eps_estimate': {
                                'value': data.get('eps', {}).get('avg'),
                                'analysts': data.get('eps', {}).get('numberOfAnalysts')
                            }
                        }
        except Exception as e:
            logger.warning(f"Failed to fetch analyst expectations: {e}")
            return None
    
    def _prepare_content(self, content: str) -> str:
        """Prepare content for processing, truncate if needed"""
        if len(content) > self.max_tokens * 3:  # Rough estimate: 1 token ≈ 3 chars
            content = content[:self.max_tokens * 3]
            logger.info(f"Truncated content to {len(content)} chars")
        return content
    
    async def _generate_text(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate text using OpenAI with configured temperature"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst with expertise in SEC filings analysis."},
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