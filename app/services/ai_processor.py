# app/services/ai_processor.py
"""
AI Processor Service
Uses OpenAI to generate summaries and analysis of SEC filings
Differentiated processing for 10-K, 10-Q, 8-K, and S-1 filings
Enhanced with structured financial data extraction
Day 20: Added market impact analysis for 10-K and 10-Q
FIXED: All extraction functions now return text narratives instead of JSON
UPDATE: 10-Q now generates financial snapshot instead of structured metrics
"""
import os
import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
from pathlib import Path

from openai import OpenAI
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.models.filing import Filing, ProcessingStatus, ManagementTone, FilingType
from app.core.config import settings
from app.services.text_extractor import text_extractor

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)


class AIProcessor:
    """
    Process filings using OpenAI to generate summaries and analysis
    """
    
    def __init__(self):
        self.model = "gpt-4o-mini"  # Updated to latest efficient model
        self.max_tokens = 16000  # Much larger context window
        
    async def process_filing(self, db: Session, filing: Filing) -> bool:
        """
        Process a filing using AI to generate summary and analysis
        Routes to specific processor based on filing type
        
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
            
            logger.info(f"Starting AI processing for {filing.company.ticker} {filing.filing_type.value}")
            
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
            
            # Route to specific processor based on filing type
            if filing.filing_type == FilingType.FORM_10K:
                result = await self._process_10k(filing, primary_content, full_text)
            elif filing.filing_type == FilingType.FORM_10Q:
                result = await self._process_10q(filing, primary_content, full_text)
            elif filing.filing_type == FilingType.FORM_8K:
                result = await self._process_8k(filing, primary_content, full_text)
            elif filing.filing_type == FilingType.FORM_S1:
                result = await self._process_s1(filing, primary_content, full_text)
            else:
                # Fallback to generic processing
                result = await self._process_generic(filing, primary_content)
            
            # Update filing with results
            filing.ai_summary = result['summary']
            
            # Store feed_summary separately (could be in a new field or embedded)
            if 'feed_summary' in result:
                # For now, prepend to summary with a marker
                filing.ai_summary = f"FEED_SUMMARY: {result['feed_summary']}\n\nFULL_SUMMARY:\n{result['summary']}"
            
            filing.management_tone = result['tone']
            filing.tone_explanation = result['tone_explanation']
            filing.key_questions = result['questions']
            filing.key_tags = result['tags']
            
            if filing.filing_type == FilingType.FORM_8K and 'event_type' in result:
                filing.event_type = result.get('event_type')
            
            # Add financial data if available (now always text)
            if 'financial_data' in result and result['financial_data']:
                filing.financial_highlights = result['financial_data']
            
            filing.status = ProcessingStatus.COMPLETED
            filing.processing_completed_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"✅ AI processing completed for {filing.accession_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error in AI processing: {e}")
            filing.status = ProcessingStatus.FAILED
            filing.error_message = str(e)
            db.commit()
            return False
    
    async def _process_10k(self, filing: Filing, primary_content: str, full_text: str) -> Dict:
        """
        Process 10-K annual report with specific focus areas
        """
        logger.info("Processing 10-K annual report")
        
        # Truncate content if needed
        content = self._prepare_content(primary_content)
        
        # Generate comprehensive annual summary
        summary_prompt = f"""You are a financial analyst. Create a comprehensive 5-minute summary of this {filing.company.name} annual report (10-K).

Focus on these key areas:
1. Annual performance highlights and key metrics
2. Geographic performance (especially mention China, India, emerging markets if discussed)
3. Business segment performance (break down by major divisions)
4. Strategic investments and R&D focus (especially AI, technology initiatives)
5. Management's forward-looking statements and guidance
6. Major risks and challenges faced during the year
7. Capital allocation decisions (dividends, buybacks, acquisitions)

Content:
{content}

Write a professional summary (400-500 words) that helps investors understand the company's annual performance and future direction."""

        summary = await self._generate_text(summary_prompt, max_tokens=1200)
        
        # Extract one-line summary
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        
        # Analyze tone
        tone_data = await self._analyze_tone(content)
        
        # Generate comprehensive Q&A
        questions = await self._generate_annual_questions(filing.company.name, content)
        
        # Extract financial data as narrative text
        financial_highlights_text = await self._extract_structured_financial_data(filing.filing_type.value, content, full_text)
        
        # Generate tags
        tags = self._generate_10k_tags(summary)
        
        # Generate market impact analysis for 10-K
        market_impact_10k = await self._generate_market_impact_10k(filing.company.name, summary, financial_highlights_text)
        
        # Store all fields including differentiated display fields
        result = {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'financial_data': financial_highlights_text,  # Now this is text
            # Differentiated display fields for 10-K - ALL NOW TEXT
            'auditor_opinion': await self._extract_auditor_opinion(full_text),
            'three_year_financials': await self._extract_three_year_financials(full_text),
            'business_segments': await self._extract_business_segments(content, full_text),
            'risk_summary': await self._extract_risk_summary(content),
            'growth_drivers': await self._generate_growth_drivers(filing.company.name, summary, financial_highlights_text),
            'management_outlook': await self._generate_management_outlook(content, summary),
            'strategic_adjustments': await self._generate_strategic_adjustments(content, summary),
            'market_impact_10k': market_impact_10k
        }
        
        # Update filing with differentiated fields
        filing.auditor_opinion = result.get('auditor_opinion')
        filing.three_year_financials = result.get('three_year_financials')
        filing.business_segments = result.get('business_segments')
        filing.risk_summary = result.get('risk_summary')
        filing.growth_drivers = result.get('growth_drivers')
        filing.management_outlook = result.get('management_outlook')
        filing.strategic_adjustments = result.get('strategic_adjustments')
        filing.market_impact_10k = result.get('market_impact_10k')
        
        return result

    async def _process_10q(self, filing: Filing, primary_content: str, full_text: str) -> Dict:
        """
        Process 10-Q quarterly report with focus on trends and changes
        UPDATED: Now generates financial snapshot instead of structured metrics
        """
        logger.info("Processing 10-Q quarterly report")
        
        content = self._prepare_content(primary_content)
        
        # Generate quarterly summary
        summary_prompt = f"""You are a financial analyst. Create a focused quarterly summary of this {filing.company.name} 10-Q filing.

Focus on:
1. Quarterly results vs expectations (if mentioned)
2. Key growth drivers this quarter
3. Margin changes and profitability trends
4. Updated guidance or outlook changes
5. Quarter-over-quarter and year-over-year comparisons
6. Significant events or changes during the quarter
7. Cash flow and balance sheet highlights

Content:
{content}

Write a concise but comprehensive summary (300-400 words) that helps investors understand quarterly performance and trends."""

        summary = await self._generate_text(summary_prompt, max_tokens=1000)
        
        # Extract one-line summary
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        
        # Analyze tone
        tone_data = await self._analyze_tone(content)
        
        # Generate quarterly Q&A
        questions = await self._generate_quarterly_questions(filing.company.name, content)
        
        # NEW: Generate financial snapshot for 10-Q (replaces structured financial data)
        financial_snapshot = await self._generate_financial_snapshot_10q(content, summary)
        
        # Generate tags
        tags = self._generate_10q_tags(summary)
        
        # Generate market impact analysis for 10-Q
        market_impact_10q = await self._generate_market_impact_10q(filing.company.name, summary, financial_snapshot)
        
        # Store all fields including differentiated display fields
        result = {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'financial_data': financial_snapshot,  # This is the financial snapshot text
            # Differentiated display fields for 10-Q - ALL NOW TEXT
            'expectations_comparison': await self._extract_expectations_comparison(content, summary),
            'cost_structure': await self._extract_cost_structure(content, full_text),
            'guidance_update': await self._extract_guidance_update(content),
            'growth_decline_analysis': await self._generate_growth_decline_analysis(summary, content),
            'management_tone_analysis': await self._generate_management_tone_analysis(content, tone_data),
            'beat_miss_analysis': await self._generate_beat_miss_analysis(summary, content),
            'market_impact_10q': market_impact_10q
        }
        
        # Update filing with differentiated fields
        filing.expectations_comparison = result.get('expectations_comparison')
        filing.cost_structure = result.get('cost_structure')
        filing.guidance_update = result.get('guidance_update')
        filing.growth_decline_analysis = result.get('growth_decline_analysis')
        filing.management_tone_analysis = result.get('management_tone_analysis')
        filing.beat_miss_analysis = result.get('beat_miss_analysis')
        filing.market_impact_10q = result.get('market_impact_10q')
        
        return result

    async def _process_8k(self, filing: Filing, primary_content: str, full_text: str) -> Dict:
        """
        Process 8-K current report with focus on specific events
        """
        logger.info("Processing 8-K current report")
        
        content = self._prepare_content(primary_content)
        
        # Identify event type from content
        event_type = self._identify_8k_event_type(content)
        
        # Generate event summary
        summary_prompt = f"""You are a financial analyst. Create a quick summary of this {filing.company.name} 8-K filing.

This appears to be about: {event_type}

Focus on:
1. What happened (the specific event or announcement)
2. When it happened or will happen
3. Who is involved (people, companies, divisions)
4. Why it matters to investors
5. Immediate impact or expected impact

Content:
{content}

Write a clear, factual summary (200-300 words) that helps investors quickly understand this event."""

        summary = await self._generate_text(summary_prompt, max_tokens=800)
        
        # Extract one-line summary
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        
        # For 8-K, tone analysis should reflect the event nature
        tone_data = await self._analyze_8k_tone(content, event_type)
        
        # Generate event-specific Q&A
        questions = await self._generate_8k_questions(filing.company.name, content, event_type)
        
        # Extract event-specific narrative
        event_narrative = await self._extract_event_narrative(event_type, content)
        
        # Generate event-specific tags
        tags = self._generate_8k_tags(summary, event_type)
        
        # Extract structured 8-K data - NOW RETURNS TEXT
        structured_data = await self._extract_8k_structured_data(content, event_type)
        
        result = {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'event_type': event_type,
            'financial_data': event_narrative,  # Event narrative instead of metrics
            # Differentiated display fields for 8-K
            'item_type': structured_data.get('item_type'),
            'items': structured_data.get('items'),
            'event_timeline': structured_data.get('event_timeline'),
            'event_nature_analysis': await self._generate_event_nature_analysis(event_type, summary),
            'market_impact_analysis': await self._generate_8k_market_impact(filing.company.name, event_type, summary),
            'key_considerations': await self._generate_key_considerations(event_type, summary)
        }
        
        # Update filing with differentiated fields
        filing.item_type = result.get('item_type')
        filing.items = result.get('items')
        filing.event_timeline = result.get('event_timeline')
        filing.event_nature_analysis = result.get('event_nature_analysis')
        filing.market_impact_analysis = result.get('market_impact_analysis')
        filing.key_considerations = result.get('key_considerations')
        
        return result

    async def _process_s1(self, filing: Filing, primary_content: str, full_text: str) -> Dict:
        """
        Process S-1 IPO registration with focus on business model and risks
        """
        logger.info("Processing S-1 IPO registration")
        
        content = self._prepare_content(primary_content)
        
        # Generate IPO overview
        summary_prompt = f"""You are a financial analyst. Create an IPO overview of this {filing.company.name} S-1 filing.

Focus on:
1. Company business model and value proposition
2. Financial snapshot (revenue, profitability, growth rates)
3. Target valuation and share price range (if disclosed)
4. Use of proceeds from IPO
5. Key risk factors specific to this business
6. Competitive advantages and market position
7. Management team and major shareholders

Content:
{content}

Write a comprehensive IPO summary (400-500 words) that helps investors evaluate this offering."""

        summary = await self._generate_text(summary_prompt, max_tokens=1200)
        
        # Extract one-line summary
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        
        # Analyze tone (usually optimistic for S-1)
        tone_data = await self._analyze_ipo_tone(content)
        
        # Generate IPO-specific Q&A
        questions = await self._generate_ipo_questions(filing.company.name, content)
        
        # Extract IPO-specific data - NOW ALL TEXT
        ipo_details = await self._extract_ipo_details(content, full_text)
        financial_summary = await self._extract_financial_summary_s1(content, full_text)
        
        # Extract financial highlights as narrative
        financial_highlights_text = await self._extract_structured_financial_data(filing.filing_type.value, content, full_text)
        
        # Generate tags
        tags = self._generate_s1_tags(summary)
        
        # Extract S-1 specific structured data
        result = {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'financial_data': financial_highlights_text,  # Now text narrative
            # Differentiated display fields for S-1 - ALL NOW TEXT
            'ipo_details': ipo_details,
            'company_overview': await self._generate_company_overview(filing.company.name, content),
            'financial_summary': financial_summary,
            'risk_categories': await self._extract_risk_categories(content),
            'growth_path_analysis': await self._generate_growth_path_analysis(filing.company.name, summary, financial_highlights_text),
            'competitive_moat_analysis': await self._generate_competitive_moat_analysis(content, summary)
        }
        
        # Update filing with differentiated fields
        filing.ipo_details = result.get('ipo_details')
        filing.company_overview = result.get('company_overview')
        filing.financial_summary = result.get('financial_summary')
        filing.risk_categories = result.get('risk_categories')
        filing.growth_path_analysis = result.get('growth_path_analysis')
        filing.competitive_moat_analysis = result.get('competitive_moat_analysis')
        
        return result

    # ====================== NEW: FINANCIAL SNAPSHOT FOR 10-Q ======================
    
    async def _generate_financial_snapshot_10q(self, content: str, summary: str) -> str:
        """Generate financial snapshot for 10-Q - the first display item"""
        prompt = f"""Create a compelling quarterly financial snapshot based on this 10-Q filing.

Content excerpt:
{content[:2000]}

Summary context:
{summary[:500]}

Write a financial snapshot (120-150 words) that:
1. Opens with the most important metric (usually revenue and growth)
2. Highlights profitability and EPS performance vs expectations
3. Notes margin trends and operational efficiency
4. Mentions cash generation or balance sheet strength
5. Ends with forward-looking context if available

Style: Write like a financial journalist's lead paragraph - punchy, informative, and engaging.

Example: "The company delivered third-quarter revenue of $8.3 billion, up 12% year-over-year, driven by robust international activity. Net income reached $1.2 billion, translating to earnings of $0.85 per share, beating consensus by $0.03. Operating margins expanded 120 basis points to 15.3%, reflecting improved pricing and operational leverage. The company generated $1.8 billion in free cash flow, strengthening an already solid balance sheet with net debt reduced to $8.5 billion. Management's confident tone and raised guidance suggest momentum continuing into the fourth quarter."

Make it narrative and insightful, not just a data dump."""

        return await self._generate_text(prompt, max_tokens=200)

    # ====================== UPDATED: FINANCIAL DATA EXTRACTOR ======================
    
    async def _extract_structured_financial_data(self, filing_type: str, content: str, full_text: str) -> str:
        """Extract financial data as narrative text instead of JSON"""
        prompt = f"""Extract and summarize key financial metrics from this {filing_type} filing.

Content:
{content[:3000]}

Write a compelling financial narrative (150-200 words) that includes:
1. Revenue figures and growth trends
2. Profitability metrics (net income, EPS)
3. Margin performance (gross and operating)
4. Balance sheet strength (cash position, debt levels)
5. Key financial ratios or metrics

Style: Write like a financial analyst's summary - informative yet engaging. Use specific numbers but weave them into a narrative.

Example: "The company delivered robust financial performance with revenue reaching $95 billion, up 8.5% year-over-year, driven by strong product demand across all segments. Net income of $20 billion translated to earnings of $5.67 per share, reflecting exceptional operational execution. Gross margins held steady at 43.2% while operating margins expanded to 29.8%, demonstrating pricing power and efficiency gains. The balance sheet remains fortress-like with $30 billion in cash against $120 billion in total debt, providing ample flexibility for strategic investments and capital returns."

Make it narrative and insightful, focusing on the story behind the numbers."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _extract_event_narrative(self, event_type: str, content: str) -> str:
        """Extract event narrative for 8-K instead of metrics"""
        prompt = f"""Create a brief financial/business impact narrative for this {event_type} event.

Content excerpt:
{content[:1500]}

Write a concise narrative (100-150 words) that explains:
1. The financial or business significance of this event
2. Any quantitative impacts mentioned (deal size, costs, etc.)
3. Strategic implications for the company
4. Timeline and implementation details

Focus on the business impact rather than just describing what happened."""

        return await self._generate_text(prompt, max_tokens=200)

    # ====================== HELPER METHODS ======================

    def _prepare_content(self, content: str) -> str:
        """Prepare content for processing, truncate if needed"""
        if len(content) > self.max_tokens * 3:  # Rough estimate: 1 token ≈ 3 chars
            content = content[:self.max_tokens * 3]
            logger.info(f"Truncated content to {len(content)} chars")
        return content

    async def _generate_text(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate text using OpenAI with error handling"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst with expertise in SEC filings analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            return ""

    async def _generate_feed_summary(self, summary: str, filing_type: str) -> str:
        """Generate a one-line summary for the feed"""
        prompt = f"""Based on this {filing_type} summary, create a single compelling sentence (max 100 characters) that captures the most important takeaway:

{summary}

Requirements:
- Must be under 100 characters
- Focus on the single most important fact or trend
- Use active voice
- Be specific with numbers when relevant"""

        return await self._generate_text(prompt, max_tokens=50)

    async def _analyze_tone(self, content: str) -> Dict:
        """Analyze management tone from filing content"""
        prompt = f"""Analyze the management tone in this filing. Classify as one of:
- OPTIMISTIC: Positive outlook, growth expectations, confidence
- CONFIDENT: Steady progress, meeting targets, stable outlook  
- NEUTRAL: Balanced view, normal operations, mixed signals
- CAUTIOUS: Some concerns, watchful stance, conservative outlook
- CONCERNED: Significant challenges, risks, negative trends

Content excerpt:
{content[:3000]}

Provide:
1. Tone classification (one word from above)
2. Brief explanation (2-3 sentences)

Format:
TONE: [classification]
EXPLANATION: [your explanation]"""

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

    async def _generate_annual_questions(self, company_name: str, content: str) -> List[Dict]:
        """Generate Q&A for annual reports"""
        prompt = f"""Generate 3 important questions investors might have about this {company_name} annual report, with brief answers.

Content excerpt:
{content[:2000]}

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
        
        return questions[:3]  # Ensure max 3 questions

    async def _generate_quarterly_questions(self, company_name: str, content: str) -> List[Dict]:
        """Generate Q&A for quarterly reports"""
        prompt = f"""Generate 3 important questions investors might have about this {company_name} quarterly report, with brief answers.

Focus on:
- Quarterly performance vs expectations
- Guidance changes
- Key metrics trends

Content excerpt:
{content[:2000]}

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

    def _generate_10k_tags(self, summary: str) -> List[str]:
        """Generate tags for 10-K filing"""
        tags = []
        
        # Check for common 10-K themes
        summary_lower = summary.lower()
        
        if any(word in summary_lower for word in ['record', 'growth', 'increase']):
            tags.append('Growth')
        if any(word in summary_lower for word in ['dividend', 'buyback', 'repurchase']):
            tags.append('Capital Return')
        if any(word in summary_lower for word in ['acquisition', 'merger', 'm&a']):
            tags.append('M&A')
        if any(word in summary_lower for word in ['restructur', 'transform']):
            tags.append('Restructuring')
        if 'ai' in summary_lower or 'artificial intelligence' in summary_lower:
            tags.append('AI Investment')
        if any(word in summary_lower for word in ['margin', 'profitability']):
            tags.append('Margins')
        
        # Always add
        tags.append('Annual Report')
        
        return list(set(tags))[:5]  # Max 5 tags

    def _generate_10q_tags(self, summary: str) -> List[str]:
        """Generate tags for 10-Q filing"""
        tags = []
        
        summary_lower = summary.lower()
        
        if any(word in summary_lower for word in ['beat', 'exceed', 'surpass']):
            tags.append('Earnings Beat')
        if any(word in summary_lower for word in ['miss', 'below', 'disappoint']):
            tags.append('Earnings Miss')
        if 'guidance' in summary_lower:
            tags.append('Guidance Update')
        if any(word in summary_lower for word in ['margin', 'profitability']):
            tags.append('Margins')
        if any(word in summary_lower for word in ['growth', 'increase']):
            tags.append('Growth')
        
        tags.append('Quarterly Results')
        
        return list(set(tags))[:5]

    def _identify_8k_event_type(self, content: str) -> str:
        """Identify the type of 8-K event from content"""
        content_lower = content.lower()
        
        # Common 8-K events
        if 'item 1.01' in content_lower or 'entry into' in content_lower:
            return "Material Agreement"
        elif 'item 2.02' in content_lower or 'results of operations' in content_lower:
            return "Earnings Release"
        elif 'item 5.02' in content_lower or ('departure' in content_lower and 'officer' in content_lower):
            return "Executive Change"
        elif 'item 7.01' in content_lower or 'regulation fd' in content_lower:
            return "Regulation FD Disclosure"
        elif 'item 8.01' in content_lower:
            return "Other Events"
        elif 'merger' in content_lower or 'acquisition' in content_lower:
            return "M&A Activity"
        elif 'dividend' in content_lower:
            return "Dividend Announcement"
        else:
            return "Corporate Event"

    def _generate_8k_tags(self, summary: str, event_type: str) -> List[str]:
        """Generate tags for 8-K filing"""
        tags = [event_type]
        
        summary_lower = summary.lower()
        
        if 'ceo' in summary_lower or 'cfo' in summary_lower or 'executive' in summary_lower:
            tags.append('Leadership Change')
        if 'earnings' in summary_lower:
            tags.append('Earnings')
        if 'acquisition' in summary_lower or 'merger' in summary_lower:
            tags.append('M&A')
        if 'dividend' in summary_lower:
            tags.append('Dividend')
        
        return list(set(tags))[:5]

    def _generate_s1_tags(self, summary: str) -> List[str]:
        """Generate tags for S-1 filing"""
        tags = ['IPO']
        
        summary_lower = summary.lower()
        
        if 'technology' in summary_lower or 'software' in summary_lower:
            tags.append('Tech IPO')
        if 'biotech' in summary_lower or 'pharmaceutical' in summary_lower:
            tags.append('Biotech IPO')
        if 'saas' in summary_lower:
            tags.append('SaaS')
        if 'ai' in summary_lower or 'artificial intelligence' in summary_lower:
            tags.append('AI')
        if 'profitable' in summary_lower:
            tags.append('Profitable')
        elif 'loss' in summary_lower:
            tags.append('Pre-Revenue')
        
        return list(set(tags))[:5]

    async def _analyze_8k_tone(self, content: str, event_type: str) -> Dict:
        """Analyze tone specific to 8-K events"""
        # For 8-K, tone often depends on event type
        if event_type == "Earnings Release":
            return await self._analyze_tone(content)
        elif event_type == "Executive Change":
            # Executive changes are usually neutral unless negative circumstances
            if any(word in content.lower() for word in ['resignation', 'termination', 'departure']):
                return {'tone': ManagementTone.CAUTIOUS, 'explanation': 'Executive departure may signal transition period'}
            else:
                return {'tone': ManagementTone.NEUTRAL, 'explanation': 'Routine executive appointment'}
        else:
            return {'tone': ManagementTone.NEUTRAL, 'explanation': f'{event_type} disclosed as required'}

    async def _generate_8k_questions(self, company_name: str, content: str, event_type: str) -> List[Dict]:
        """Generate event-specific questions for 8-K"""
        prompt = f"""Generate 2 important questions investors might have about this {company_name} {event_type} announcement, with brief answers.

Content excerpt:
{content[:1500]}

Format each as:
Q: [Question]
A: [Brief answer, 2-3 sentences]"""

        response = await self._generate_text(prompt, max_tokens=300)
        
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
        
        return questions[:2]

    async def _analyze_ipo_tone(self, content: str) -> Dict:
        """Analyze tone for S-1 filings (usually optimistic)"""
        # S-1 filings are typically optimistic as companies are selling their story
        return {
            'tone': ManagementTone.OPTIMISTIC,
            'explanation': 'Company presenting growth story and market opportunity for IPO'
        }

    async def _generate_ipo_questions(self, company_name: str, content: str) -> List[Dict]:
        """Generate IPO-specific questions"""
        prompt = f"""Generate 3 important questions investors might have about this {company_name} IPO, with brief answers.

Focus on:
- Business model viability
- Path to profitability
- Competitive advantages
- Use of proceeds

Content excerpt:
{content[:2000]}

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

    # ====================== DIFFERENTIATED DISPLAY FIELD EXTRACTORS (ALL TEXT) ======================

    async def _extract_auditor_opinion(self, full_text: str) -> str:
        """Extract auditor opinion from 10-K"""
        prompt = f"""Extract the auditor's opinion from this 10-K filing. Look for the auditor's report section.

Content excerpt:
{full_text[:5000]}

Provide a brief summary of the auditor's opinion (e.g., "Unqualified opinion from PwC" or "Clean opinion from Deloitte with no material weaknesses")"""

        return await self._generate_text(prompt, max_tokens=100)

    async def _extract_three_year_financials(self, full_text: str) -> str:
        """Extract 3-year financial trends from 10-K - NOW RETURNS TEXT"""
        prompt = f"""Analyze the 3-year financial data from this 10-K filing.

Content:
{full_text[:5000]}

Write a narrative summary (150-200 words) describing:
1. Revenue trend over the past 3 years (growth rate, key drivers)
2. Net income/profitability trend
3. Margin evolution (gross and operating margins)
4. Key financial ratios and their changes
5. Overall financial trajectory

Focus on telling the financial story, not just listing numbers."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _extract_business_segments(self, content: str, full_text: str) -> str:
        """Extract business segment breakdown - NOW RETURNS TEXT"""
        prompt = f"""Analyze the business segment information from this 10-K filing.

Content:
{content[:3000]}

Write a narrative summary (150-200 words) describing:
1. Major business segments and their revenue contribution
2. Relative performance of each segment
3. Growth rates by segment
4. Geographic breakdown if available
5. Strategic importance of each segment

Present as a cohesive narrative, not a list."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _extract_risk_summary(self, content: str) -> str:
        """Extract and categorize key risks - NOW RETURNS TEXT"""
        prompt = f"""Analyze and summarize the key risk factors from this 10-K filing.

Content excerpt:
{content[:3000]}

Write a narrative summary (150-200 words) covering:
1. Most critical operational risks
2. Key financial and market risks
3. Regulatory and compliance challenges
4. Competitive threats
5. Technology or disruption risks

Group them logically but present as flowing text, not lists."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_growth_drivers(self, company_name: str, summary: str, financial_narrative: str) -> str:
        """Generate analysis of growth drivers"""
        prompt = f"""Based on this {company_name} annual report summary and financial performance, identify and explain the key growth drivers.

Summary:
{summary[:1000]}

Financial performance:
{financial_narrative}

Provide a concise analysis (150-200 words) of:
1. Primary growth drivers
2. Emerging growth opportunities
3. Growth sustainability factors"""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_management_outlook(self, content: str, summary: str) -> str:
        """Extract and analyze management's forward-looking statements"""
        prompt = f"""Analyze management's outlook and forward-looking statements from this annual report.

Summary:
{summary[:1000]}

Content excerpt:
{content[:2000]}

Provide a concise summary (150-200 words) of:
1. Management's view on future prospects
2. Key priorities mentioned
3. Tone of forward guidance"""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_strategic_adjustments(self, content: str, summary: str) -> str:
        """Identify strategic changes or pivots"""
        prompt = f"""Identify any strategic adjustments or changes in direction from this annual report.

Summary:
{summary[:1000]}

Look for:
1. New strategic initiatives
2. Changes in business focus
3. Market expansion or contraction
4. Technology or product pivots

Provide a concise analysis (150-200 words)."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_market_impact_10k(self, company_name: str, summary: str, financial_narrative: str) -> str:
        """Generate market impact analysis for 10-K"""
        prompt = f"""You are a senior financial analyst. Based on this {company_name} annual report (10-K), analyze the potential market impact.

Summary content:
{summary}

Financial performance:
{financial_narrative}

Please analyze:
1. Points that may attract positive market attention
2. Aspects that may need continued market observation
3. Potential impact of long-term strategic adjustments on valuation
4. Relative performance compared to peers

Requirements:
- Use soft expressions like "may", "could", "worth noting"
- Avoid predicting specific price movements
- Focus on fundamental analysis
- Keep it 200-300 words"""

        return await self._generate_text(prompt, max_tokens=600)

    async def _extract_expectations_comparison(self, content: str, summary: str) -> str:
        """Extract actual vs expected metrics for 10-Q - NOW RETURNS TEXT"""
        prompt = f"""Analyze how the company performed versus market expectations in this quarterly report.

Content:
{content[:2000]}

Summary:
{summary[:1000]}

Write a narrative summary (150-200 words) describing:
1. How actual results compared to consensus estimates
2. Key metrics that beat or missed expectations
3. Revenue and EPS performance vs guidance
4. Market reaction drivers
5. Management's explanation for variances

Present as a cohesive analysis, not raw data."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _extract_cost_structure(self, content: str, full_text: str) -> str:
        """Extract cost structure breakdown for 10-Q - NOW RETURNS TEXT"""
        prompt = f"""Analyze the cost structure from this quarterly report.

Content:
{content[:2000]}

Write a narrative summary (150-200 words) describing:
1. Major cost categories as percentage of revenue
2. Year-over-year changes in cost structure
3. Operating leverage trends
4. R&D and SG&A spending patterns
5. Margin improvement or pressure areas

Focus on trends and insights, not just numbers."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _extract_guidance_update(self, content: str) -> str:
        """Extract guidance updates from 10-Q - NOW RETURNS TEXT"""
        prompt = f"""Analyze any guidance updates from this quarterly report.

Content:
{content[:2000]}

Write a narrative summary (100-150 words) covering:
1. Whether guidance was raised, lowered, or maintained
2. New guidance ranges for key metrics
3. Key assumptions and drivers
4. Changes from previous guidance
5. Management confidence level

If no guidance update, state that clearly."""

        return await self._generate_text(prompt, max_tokens=250)

    async def _generate_growth_decline_analysis(self, summary: str, content: str) -> str:
        """Analyze growth or decline drivers for 10-Q"""
        prompt = f"""Based on this quarterly report summary and content, analyze what drove growth or decline this quarter.

Summary:
{summary[:1000]}

Content excerpt:
{content[:1000]}

Provide a concise analysis (150-200 words) of:
1. Key growth or decline drivers
2. Segment performance
3. Geographic variations
4. One-time vs recurring factors"""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_management_tone_analysis(self, content: str, tone_data: Dict) -> str:
        """Detailed analysis of management tone for 10-Q"""
        prompt = f"""Provide a detailed analysis of management's tone and messaging in this quarterly report.

Current tone assessment: {tone_data.get('tone', 'NEUTRAL')}
Explanation: {tone_data.get('explanation', '')}

Content excerpt:
{content[:1500]}

Analyze:
1. Confidence level in guidance
2. Discussion of challenges vs opportunities
3. Change in tone from previous quarters (if mentioned)
4. Key phrases that indicate sentiment

Provide concise analysis (150-200 words)."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_beat_miss_analysis(self, summary: str, content: str) -> str:
        """Analyze reasons for beating or missing expectations"""
        prompt = f"""Based on this quarterly report, analyze why the company beat or missed expectations.

Summary:
{summary[:1000]}

Content excerpt:
{content[:1000]}

Provide a concise analysis (150-200 words) of:
1. Specific factors that led to outperformance or underperformance
2. Whether these factors are likely to persist
3. Management's explanation
4. Market's likely interpretation"""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_market_impact_10q(self, company_name: str, summary: str, financial_narrative: str) -> str:
        """Generate market impact analysis for 10-Q"""
        prompt = f"""You are a senior financial analyst. Based on this {company_name} quarterly report (10-Q), analyze the potential short-term market impact.

Summary content:
{summary}

Financial performance:
{financial_narrative}

Please analyze:
1. Performance vs market expectations
2. Points that may trigger short-term market reactions
3. Market implications of guidance adjustments
4. Quarterly performance compared to industry peers

Requirements:
- Use soft expressions like "may", "could", "worth noting"
- Avoid predicting specific price movements
- Focus on short-term performance drivers
- Keep it 200-300 words"""

        return await self._generate_text(prompt, max_tokens=600)

    async def _extract_8k_structured_data(self, content: str, event_type: str) -> Dict:
        """Extract structured data specific to 8-K filings - NOW RETURNS TEXT FOR ITEMS AND TIMELINE"""
        # Extract Item number
        item_pattern = r'Item\s+(\d+\.\d+)'
        item_match = re.search(item_pattern, content, re.IGNORECASE)
        item_type = item_match.group(1) if item_match else None
        
        # Generate text description for items
        items_prompt = f"""Based on this 8-K filing with Item {item_type or 'Unknown'}, describe what was reported.

Event type: {event_type}
Content excerpt:
{content[:1000]}

Write a brief description (50-100 words) of the reported items and their significance."""

        items_text = await self._generate_text(items_prompt, max_tokens=150)
        
        # Generate text description for timeline
        timeline_prompt = f"""Analyze the timeline of events in this 8-K filing.

Content excerpt:
{content[:1000]}

Write a brief timeline narrative (50-100 words) describing when key events occurred or will occur."""

        timeline_text = await self._generate_text(timeline_prompt, max_tokens=150)
        
        return {
            'item_type': item_type,
            'items': items_text,
            'event_timeline': timeline_text
        }

    async def _generate_event_nature_analysis(self, event_type: str, summary: str) -> str:
        """Analyze the nature and significance of 8-K event"""
        prompt = f"""Analyze the nature and significance of this {event_type} event.

Summary:
{summary}

Provide a concise analysis (100-150 words) covering:
1. Type and nature of the event
2. Materiality to the company
3. Typical market interpretation of such events
4. Required regulatory disclosure aspects"""

        return await self._generate_text(prompt, max_tokens=250)

    async def _generate_8k_market_impact(self, company_name: str, event_type: str, summary: str) -> str:
        """Generate market impact analysis for 8-K events"""
        prompt = f"""Analyze the potential market impact of this {company_name} {event_type} announcement.

Summary:
{summary}

Provide a balanced analysis (150-200 words) of:
1. Immediate market reaction expectations
2. Longer-term implications
3. Impact on specific stakeholder groups
4. Comparison to similar events in the industry

Use soft language like "may", "could", "potentially". Avoid specific price predictions."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_key_considerations(self, event_type: str, summary: str) -> str:
        """Generate key considerations for investors regarding 8-K event"""
        prompt = f"""Based on this {event_type} announcement, what are the key considerations for investors?

Summary:
{summary}

List 3-4 key points investors should consider, such as:
- Impact on operations
- Financial implications
- Strategic changes
- Timeline of effects

Be concise and factual (100-150 words total)."""

        return await self._generate_text(prompt, max_tokens=250)

    async def _extract_ipo_details(self, content: str, full_text: str) -> str:
        """Extract IPO details from S-1 - NOW RETURNS TEXT"""
        prompt = f"""Analyze the IPO details from this S-1 filing.

Content:
{content[:3000]}

Write a narrative summary (150-200 words) covering:
1. Proposed ticker symbol and exchange
2. Expected price range and valuation
3. Number of shares offered
4. Lead underwriters
5. Use of proceeds
6. Lock-up periods and key dates

Present as a cohesive overview, not a data dump."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _extract_financial_summary_s1(self, content: str, full_text: str) -> str:
        """Extract financial summary for S-1 - NOW RETURNS TEXT"""
        prompt = f"""Analyze the financial summary from this S-1 IPO filing.

Content:
{content[:3000]}

Write a narrative summary (150-200 words) covering:
1. Revenue trajectory and growth rate
2. Path to profitability (or current profitability)
3. Cash burn rate and runway
4. Unit economics and key metrics
5. Financial position strength

Focus on the investment story, not just raw numbers."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_company_overview(self, company_name: str, content: str) -> str:
        """Generate company overview for S-1"""
        prompt = f"""Create a concise company overview for {company_name} based on their S-1 filing.

Content:
{content[:2000]}

Include:
1. What the company does (business model)
2. Target market and customers
3. Key products or services
4. Founding story and timeline
5. Current scale (employees, customers, geographic presence)

Keep it to 200-250 words."""

        return await self._generate_text(prompt, max_tokens=400)

    async def _extract_risk_categories(self, content: str) -> str:
        """Extract and categorize risks for S-1 - NOW RETURNS TEXT"""
        prompt = f"""Analyze the risk factors from this S-1 filing.

Content excerpt:
{content[:3000]}

Write a narrative summary (150-200 words) covering:
1. Core business model risks
2. Market and competitive risks
3. Regulatory and legal challenges
4. Financial and liquidity risks
5. Technology and execution risks

Weave these into a cohesive risk overview, not separate categories."""

        return await self._generate_text(prompt, max_tokens=300)

    async def _generate_growth_path_analysis(self, company_name: str, summary: str, financial_narrative: str) -> str:
        """Analyze growth path for S-1 companies"""
        prompt = f"""Analyze the growth path and potential for {company_name} based on their S-1 filing.

Summary:
{summary[:1000]}

Financial performance:
{financial_narrative}

Provide analysis (200-250 words) of:
1. Historical growth trajectory
2. Market opportunity size
3. Growth strategy and expansion plans
4. Key metrics and milestones
5. Path to profitability (if applicable)"""

        return await self._generate_text(prompt, max_tokens=400)

    async def _generate_competitive_moat_analysis(self, content: str, summary: str) -> str:
        """Analyze competitive advantages for S-1 companies"""
        prompt = f"""Analyze the competitive moat and differentiation based on this S-1 filing.

Summary:
{summary[:1000]}

Content excerpt:
{content[:1500]}

Provide analysis (200-250 words) of:
1. Unique value proposition
2. Competitive advantages
3. Barriers to entry
4. Network effects or switching costs
5. Technology or IP advantages"""

        return await self._generate_text(prompt, max_tokens=400)

    async def _process_generic(self, filing: Filing, primary_content: str) -> Dict:
        """Generic processing fallback for other filing types"""
        logger.info(f"Processing generic filing type: {filing.filing_type.value}")
        
        content = self._prepare_content(primary_content)
        
        # Generate basic summary
        summary = await self._generate_summary(filing.company.name, filing.filing_type.value, content)
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        tone_data = await self._analyze_tone(content)
        questions = await self._generate_questions(filing.company.name, filing.filing_type.value, content)
        tags = self._generate_tags(filing.filing_type.value, summary)
        
        return {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags
        }

    async def _generate_summary(self, company_name: str, filing_type: str, content: str) -> str:
        """Generate generic summary"""
        prompt = f"""Create a comprehensive summary of this {company_name} {filing_type} filing.

Content:
{content[:3000]}

Write a professional summary (300-400 words) covering key points and takeaways."""

        return await self._generate_text(prompt, max_tokens=1000)

    async def _generate_questions(self, company_name: str, filing_type: str, content: str) -> List[Dict]:
        """Generate generic Q&A"""
        prompt = f"""Generate 3 important questions investors might have about this {company_name} {filing_type}, with brief answers.

Content excerpt:
{content[:1500]}

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

    def _generate_tags(self, filing_type: str, summary: str) -> List[str]:
        """Generate generic tags"""
        tags = [filing_type.replace('FORM_', '').replace('_', '-')]
        
        summary_lower = summary.lower()
        
        # Add some common tags based on content
        if 'acquisition' in summary_lower:
            tags.append('M&A')
        if 'earnings' in summary_lower:
            tags.append('Earnings')
        if 'restructuring' in summary_lower:
            tags.append('Restructuring')
        
        return tags[:5]


# Initialize singleton
ai_processor = AIProcessor()