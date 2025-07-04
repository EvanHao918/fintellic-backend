# app/services/ai_processor.py
"""
AI Processor Service
Uses OpenAI to generate summaries and analysis of SEC filings
Differentiated processing for 10-K, 10-Q, 8-K, and S-1 filings
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
            
            # Add financial data if available
            if 'financial_data' in result:
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
        
        # Extract one-line summary for feed
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        
        # Analyze management tone
        tone_data = await self._analyze_tone(content)
        
        # Generate comprehensive Q&A
        questions = await self._generate_annual_questions(filing.company.name, content)
        
        # Extract financial data
        financial_data = self._extract_financial_data(full_text)
        
        # Generate tags
        tags = self._generate_10k_tags(summary, financial_data)
        
        return {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'financial_data': financial_data
        }
    
    async def _process_10q(self, filing: Filing, primary_content: str, full_text: str) -> Dict:
        """
        Process 10-Q quarterly report with focus on quarterly performance
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
        
        # Extract financial data
        financial_data = self._extract_financial_data(full_text)
        
        # Generate tags
        tags = self._generate_10q_tags(summary)
        
        return {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'financial_data': financial_data
        }
    
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
        
        # Generate event-specific tags
        tags = self._generate_8k_tags(summary, event_type)
        
        return {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'event_type': event_type
        }
    
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
        feed_summary = await self._generate_feed_summary(summary, "IPO Filing")
        
        # For S-1, analyze the "story" being told
        tone_data = await self._analyze_ipo_tone(content)
        
        # Generate IPO-specific Q&A
        questions = await self._generate_ipo_questions(filing.company.name, content)
        
        # Extract financial history if available
        financial_data = self._extract_ipo_financials(full_text)
        
        # Generate IPO tags
        tags = self._generate_s1_tags(summary)
        
        return {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags,
            'financial_data': financial_data,
            'event_type': event_type  # 确保这一行存在
        }
    
    async def _process_generic(self, filing: Filing, primary_content: str) -> Dict:
        """
        Generic processing fallback for other filing types
        """
        content = self._prepare_content(primary_content)
        
        summary = await self._generate_summary(filing.company.name, filing.filing_type.value, content)
        feed_summary = await self._generate_feed_summary(summary, filing.filing_type.value)
        tone_data = await self._analyze_tone(content)
        questions = await self._generate_questions(filing.company.name, filing.filing_type.value, content)
        tags = self._extract_tags(summary)
        
        return {
            'summary': summary,
            'feed_summary': feed_summary,
            'tone': tone_data['tone'],
            'tone_explanation': tone_data['explanation'],
            'questions': questions,
            'tags': tags
        }
    
    def _prepare_content(self, content: str, max_chars: int = 45000) -> str:
        """
        Prepare content for AI processing, truncating if necessary
        """
        if len(content) > max_chars:
            logger.info(f"Truncating content from {len(content)} to {max_chars} chars")
            return content[:max_chars]
        return content
    
    def _identify_8k_event_type(self, content: str) -> str:
        """
        Identify the type of 8-K event from content
        """
        # Common 8-K item patterns
        event_mapping = {
            r"item\s*1\.01": "Entry into Material Agreement",
            r"item\s*1\.02": "Termination of Material Agreement",
            r"item\s*2\.01": "Completion of Acquisition or Disposition",
            r"item\s*2\.02": "Results of Operations",
            r"item\s*2\.03": "Material Direct Financial Obligation",
            r"item\s*3\.01": "Notice of Delisting",
            r"item\s*3\.02": "Unregistered Sales of Securities",
            r"item\s*4\.01": "Changes in Accountant",
            r"item\s*5\.01": "Changes in Control",
            r"item\s*5\.02": "Executive Officer Changes",
            r"item\s*5\.03": "Amendments to Corporate Governance",
            r"item\s*7\.01": "Regulation FD Disclosure",
            r"item\s*8\.01": "Other Events"
        }
        
        content_lower = content.lower()
        
        for pattern, event_type in event_mapping.items():
            if re.search(pattern, content_lower):
                return event_type
        
        # Try to infer from content
        if "ceo" in content_lower or "cfo" in content_lower or "executive" in content_lower:
            return "Executive Changes"
        elif "earnings" in content_lower or "results" in content_lower:
            return "Earnings Results"
        elif "acquisition" in content_lower or "merger" in content_lower:
            return "Merger/Acquisition"
        elif "dividend" in content_lower:
            return "Dividend Announcement"
        elif "debt" in content_lower or "note" in content_lower or "bond" in content_lower:
            return "Debt Issuance"
        
        return "Material Event"
    
    def _extract_financial_data(self, full_text: str) -> Dict:
        """
        Extract financial data from filing text (10-K and 10-Q)
        """
        financial_data = {}
        
        # Define patterns for common financial metrics
        patterns = {
            'revenue': [
                r"(?:total\s+)?(?:net\s+)?revenues?\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
                r"(?:total\s+)?(?:net\s+)?sales\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
            ],
            'net_income': [
                r"net\s+income\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
                r"net\s+earnings?\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
            ],
            'eps': [
                r"(?:diluted\s+)?earnings?\s+per\s+share\s*[:=]\s*\$?([\d.]+)",
                r"(?:diluted\s+)?eps\s*[:=]\s*\$?([\d.]+)",
            ],
            'total_assets': [
                r"total\s+assets\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
            ],
            'total_liabilities': [
                r"total\s+liabilities\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
            ],
            'cash': [
                r"cash\s+and\s+cash\s+equivalents\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
            ],
            'operating_cash_flow': [
                r"(?:net\s+)?cash\s+(?:provided\s+by|from)\s+operating\s+activities\s*[:=]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?",
            ]
        }
        
        text_lower = full_text.lower()
        
        for metric, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text_lower)
                if match:
                    value = match.group(1).replace(',', '')
                    # Check if it's in billions or millions
                    if 'billion' in match.group(0):
                        value = float(value) * 1000  # Convert to millions
                    financial_data[metric] = f"${value}M"
                    break
        
        return financial_data
    
    def _extract_ipo_financials(self, full_text: str) -> Dict:
        """
        Extract financial history from S-1 filing
        """
        financial_data = {}
        
        # Look for revenue trends
        revenue_pattern = r"(?:fiscal\s+)?(?:year\s+)?(\d{4})\s*[:]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:billion|million)?"
        
        matches = re.findall(revenue_pattern, full_text.lower())
        if matches:
            revenue_history = {}
            for year, amount in matches[-3:]:  # Last 3 years
                revenue_history[f"revenue_{year}"] = f"${amount.replace(',', '')}M"
            financial_data.update(revenue_history)
        
        return financial_data
    
    # Tag generation methods for each filing type
    def _generate_10k_tags(self, summary: str, financial_data: Dict) -> List[str]:
        """Generate tags for 10-K filing"""
        tags = []
        summary_lower = summary.lower()
        
        # Performance tags
        if "record" in summary_lower and "revenue" in summary_lower:
            tags.append("#RecordRevenue")
        if "growth" in summary_lower:
            tags.append("#Growth")
        if "decline" in summary_lower or "decrease" in summary_lower:
            tags.append("#Challenges")
        
        # Geographic tags
        if "china" in summary_lower:
            if "challenge" in summary_lower or "headwind" in summary_lower:
                tags.append("#ChinaChallenges")
            else:
                tags.append("#ChinaGrowth")
        if "india" in summary_lower:
            tags.append("#IndiaGrowth")
        
        # Strategic tags
        if "ai" in summary_lower or "artificial intelligence" in summary_lower:
            tags.append("#AIInvestment")
        if "acquisition" in summary_lower or "m&a" in summary_lower:
            tags.append("#M&A")
        if "dividend" in summary_lower:
            tags.append("#Dividend")
        if "buyback" in summary_lower:
            tags.append("#Buyback")
        
        # Ensure at least one tag
        if not tags:
            tags.append("#AnnualReport")
        
        return tags[:5]  # Limit to 5 tags
    
    def _generate_10q_tags(self, summary: str) -> List[str]:
        """Generate tags for 10-Q filing"""
        tags = []
        summary_lower = summary.lower()
        
        if "beat" in summary_lower and "expectation" in summary_lower:
            tags.append("#BeatExpectations")
        if "miss" in summary_lower and "expectation" in summary_lower:
            tags.append("#MissedExpectations")
        if "margin" in summary_lower and "expansion" in summary_lower:
            tags.append("#MarginExpansion")
        if "cloud" in summary_lower and "growth" in summary_lower:
            tags.append("#CloudGrowth")
        if "ai" in summary_lower and "demand" in summary_lower:
            tags.append("#AIdemand")
        if "guidance" in summary_lower and ("raise" in summary_lower or "up" in summary_lower):
            tags.append("#GuidanceUp")
        
        # Ensure at least one tag
        if not tags:
            tags.append("#QuarterlyResults")
        
        return tags[:5]
    
    def _generate_8k_tags(self, summary: str, event_type: str) -> List[str]:
        """Generate tags for 8-K filing"""
        tags = []
        summary_lower = summary.lower()
        
        # Event-specific tags
        if "Executive" in event_type:
            tags.append("#ExecutiveChange")
        elif "Material Agreement" in event_type:
            tags.append("#MaterialAgreement")
        elif "Financial Obligation" in event_type or "Debt Issuance" in event_type:
            tags.append("#DebtIssuance")
        elif "Results" in event_type:
            tags.append("#EarningsUpdate")
        elif "Acquisition" in event_type:
            tags.append("#M&A")
        
        # Content-based tags
        if "note" in summary_lower and ("issuance" in summary_lower or "issue" in summary_lower):
            tags.append("#DebtOffering")
        
        # Amount extraction
        amount_pattern = r'\$?([\d,]+(?:\.\d+)?)\s*(billion|million)'
        matches = re.findall(amount_pattern, summary_lower)
        if matches:
            # Get the largest amount mentioned
            amounts = []
            for amount_str, unit in matches:
                amount = float(amount_str.replace(',', ''))
                if unit == 'billion':
                    amount *= 1000  # Convert to millions
                amounts.append((amount, amount_str, unit))
            
            if amounts:
                largest = max(amounts, key=lambda x: x[0])
                if largest[2] == 'billion':
                    tags.append(f"#${largest[1]}B")
                else:
                    tags.append(f"#${largest[1]}M")
        
        # Date extraction
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                  'july', 'august', 'september', 'october', 'november', 'december']
        for month in months:
            if month in summary_lower:
                # Try to find year
                year_pattern = f"{month}\\s+\\d{{1,2}},?\\s+(\\d{{4}})"
                year_match = re.search(year_pattern, summary_lower)
                if year_match:
                    year = year_match.group(1)
                    tags.append(f"#{month.capitalize()}{year}")
                    break
        
        # Person/role tags
        if "ceo" in summary_lower:
            tags.append("#CEOChange")
        if "cfo" in summary_lower:
            tags.append("#CFOChange")
        
        # Other common 8-K tags
        if "internal" in summary_lower and "promotion" in summary_lower:
            tags.append("#InternalPromotion")
        if "external" in summary_lower and "hire" in summary_lower:
            tags.append("#ExternalHire")
        
        # Ensure we always have at least one tag
        if not tags:
            tags.append("#CorporateUpdate")
        
        return tags[:4]  # Limit to 4 tags for 8-K
    
    def _generate_s1_tags(self, summary: str) -> List[str]:
        """Generate tags for S-1 filing"""
        tags = []
        summary_lower = summary.lower()
        
        # Always include IPO tag
        tags.append("#IPO")
        
        # Exchange tags
        if "nyse" in summary_lower:
            tags.append("#NYSEListing")
        elif "nasdaq" in summary_lower:
            tags.append("#NASDAQListing")
        
        # Valuation tags
        valuation_pattern = r"\$?([\d,]+(?:\.\d+)?)\s*billion\s*valuation"
        val_match = re.search(valuation_pattern, summary_lower)
        if val_match:
            amount = val_match.group(1).replace(',', '')
            tags.append(f"#${amount}BValuation")
        
        # Price range tags
        price_pattern = r"\$(\d+)-(\d+)(?:/|per\s+)share"
        price_match = re.search(price_pattern, summary_lower)
        if price_match:
            tags.append(f"#${price_match.group(1)}-{price_match.group(2)}/share")
        
        # Industry tags
        if "social media" in summary_lower:
            tags.append("#SocialMedia")
        elif "technology" in summary_lower or "tech" in summary_lower:
            tags.append("#TechIPO")
        elif "biotech" in summary_lower:
            tags.append("#BiotechIPO")
        elif "fintech" in summary_lower:
            tags.append("#FintechIPO")
        
        return tags[:4]
    
    # Helper methods for async OpenAI calls
    async def _generate_text(self, prompt: str, max_tokens: int = 1000) -> str:
        """Generate text using OpenAI"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst. Provide clear, concise analysis without using emojis or informal language."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return f"Analysis generation failed: {str(e)}"
    
    async def _generate_feed_summary(self, full_summary: str, filing_type: str) -> str:
        """Generate one-line summary for feed display"""
        prompt = f"""Based on this {filing_type} summary, create a single compelling sentence (max 15 words) that captures the most important point for investors. Focus on what matters most - performance, major changes, or key events.

Summary:
{full_summary[:500]}

Write just one clear, impactful sentence:"""

        response = await self._generate_text(prompt, max_tokens=50)
        # Clean up the response
        response = response.strip().strip('"').strip("'")
        if not response.endswith('.'):
            response += '.'
        return response
    
    async def _analyze_tone(self, content: str) -> Dict:
        """
        Analyze the management tone in the filing
        """
        prompt = f"""Analyze the tone of this SEC filing text and classify it as one of:
- OPTIMISTIC: Positive outlook, growth emphasis, confident language
- CONFIDENT: Steady progress, meeting targets, controlled growth
- NEUTRAL: Balanced reporting, factual, no strong positive/negative emphasis
- CAUTIOUS: Emphasizing challenges, conservative outlook, risk-focused
- CONCERNED: Significant risks, defensive language, problems highlighted

Text:
{content[:3000]}

Respond in JSON format:
{{
    "tone": "TONE_CLASSIFICATION",
    "explanation": "Brief explanation (50-100 words) of why this tone was identified"
}}"""

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial sentiment analyst. Analyze tone objectively."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.2
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                # Remove markdown code block markers if present
                if result.startswith('```json'):
                    result = result[7:]
                if result.startswith('```'):
                    result = result[3:]
                if result.endswith('```'):
                    result = result[:-3]
                
                result = result.strip()
                
                tone_data = json.loads(result)
                tone_map = {
                    'OPTIMISTIC': ManagementTone.OPTIMISTIC,
                    'CONFIDENT': ManagementTone.CONFIDENT,
                    'NEUTRAL': ManagementTone.NEUTRAL,
                    'CAUTIOUS': ManagementTone.CAUTIOUS,
                    'CONCERNED': ManagementTone.CONCERNED
                }
                
                return {
                    'tone': tone_map.get(tone_data['tone'], ManagementTone.NEUTRAL),
                    'explanation': tone_data['explanation']
                }
            except:
                return {
                    'tone': ManagementTone.NEUTRAL,
                    'explanation': 'Unable to determine tone'
                }
                
        except Exception as e:
            logger.error(f"Tone analysis error: {e}")
            return {
                'tone': ManagementTone.NEUTRAL,
                'explanation': f'Analysis failed: {str(e)}'
            }
    
    async def _analyze_8k_tone(self, content: str, event_type: str) -> Dict:
        """Analyze tone for 8-K filings based on event type"""
        prompt = f"""This is an 8-K filing about: {event_type}

Analyze the tone considering the nature of this event. For 8-K filings, tone should reflect:
- OPTIMISTIC: Positive developments (promotions, good earnings, expansion)
- CONFIDENT: Planned transitions, meeting expectations
- NEUTRAL: Routine disclosures, regular updates
- CAUTIOUS: Challenges being addressed, transitions
- CONCERNED: Negative events, departures, missed targets

Text:
{content[:2000]}

Respond in JSON format:
{{
    "tone": "TONE_CLASSIFICATION",
    "explanation": "Brief explanation (50-100 words)"
}}"""

        return await self._analyze_tone_with_prompt(prompt)
    
    async def _analyze_ipo_tone(self, content: str) -> Dict:
        """Analyze the tone/story of S-1 IPO filing"""
        prompt = f"""Analyze the tone of this IPO S-1 filing. For IPO filings, assess:
- OPTIMISTIC: Strong growth story, market leadership claims, aggressive projections
- CONFIDENT: Solid fundamentals, clear path to profitability, reasonable claims
- NEUTRAL: Balanced presentation of opportunities and risks
- CAUTIOUS: Heavy emphasis on risks, conservative projections
- CONCERNED: Significant losses, unclear path to profitability, many risk factors

Text:
{content[:3000]}

Classify the overall IPO story as "Ambitious yet Honest", "Aggressive", "Conservative", or "Balanced".

Respond in JSON format:
{{
    "tone": "TONE_CLASSIFICATION",
    "explanation": "Analysis of the IPO narrative and tone (50-100 words)"
}}"""

        return await self._analyze_tone_with_prompt(prompt)
    
    async def _analyze_tone_with_prompt(self, prompt: str) -> Dict:
        """Helper method to analyze tone with custom prompt"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.2
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON
            if result.startswith('```'):
                result = result.split('```')[1]
                if result.startswith('json'):
                    result = result[4:]
            
            tone_data = json.loads(result.strip())
            
            tone_map = {
                'OPTIMISTIC': ManagementTone.OPTIMISTIC,
                'CONFIDENT': ManagementTone.CONFIDENT,
                'NEUTRAL': ManagementTone.NEUTRAL,
                'CAUTIOUS': ManagementTone.CAUTIOUS,
                'CONCERNED': ManagementTone.CONCERNED
            }
            
            return {
                'tone': tone_map.get(tone_data['tone'], ManagementTone.NEUTRAL),
                'explanation': tone_data['explanation']
            }
            
        except Exception as e:
            logger.error(f"Tone analysis error: {e}")
            return {
                'tone': ManagementTone.NEUTRAL,
                'explanation': 'Analysis failed'
            }
    
    # Question generation methods for each filing type
    async def _generate_annual_questions(self, company_name: str, content: str) -> List[Dict]:
        """Generate Q&A for annual reports"""
        prompt = f"""Based on this {company_name} annual report, generate 4-5 key questions an investor would ask, with answers from the filing.

Focus on:
1. Annual performance vs prior year
2. Geographic/segment performance
3. Strategic initiatives and investments
4. Outlook and guidance
5. Major risks or challenges

Content:
{content[:3000]}

Format as JSON array:
[
    {{
        "question": "Clear, specific question",
        "answer": "Factual answer based on filing (50-100 words)"
    }}
]"""

        return await self._generate_qa_json(prompt)
    
    async def _generate_quarterly_questions(self, company_name: str, content: str) -> List[Dict]:
        """Generate Q&A for quarterly reports"""
        prompt = f"""Based on this {company_name} quarterly report, generate 3-4 key questions about:

1. Quarterly performance vs expectations
2. Growth drivers this quarter
3. Margin and profitability trends
4. Updated outlook or guidance

Content:
{content[:2500]}

Format as JSON array:
[
    {{
        "question": "Specific quarterly question",
        "answer": "Answer from filing (50-100 words)"
    }}
]"""

        return await self._generate_qa_json(prompt)
    
    async def _generate_8k_questions(self, company_name: str, content: str, event_type: str) -> List[Dict]:
        """Generate Q&A for 8-K events"""
        prompt = f"""Based on this {company_name} 8-K filing about {event_type}, generate 3-4 key questions:

1. What exactly happened?
2. When does it take effect?
3. Why did this occur?
4. What's the impact?

Content:
{content[:2000]}

Format as JSON array with short, factual answers (30-70 words each)."""

        return await self._generate_qa_json(prompt)
    
    async def _generate_ipo_questions(self, company_name: str, content: str) -> List[Dict]:
        """Generate Q&A for IPO filings"""
        prompt = f"""Based on this {company_name} S-1 IPO filing, generate 4-5 key investor questions:

1. Why go public now?
2. Is the business model proven?
3. Path to profitability?
4. Main risk factors?
5. Valuation justification?

Content:
{content[:3000]}

Format as JSON array focusing on IPO-specific concerns."""

        return await self._generate_qa_json(prompt)
    
    async def _generate_qa_json(self, prompt: str) -> List[Dict]:
        """Helper to generate Q&A in JSON format"""
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Generate clear Q&A without speculation."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.3
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON
            if result.startswith('```'):
                result = result.split('```')[1]
                if result.startswith('json'):
                    result = result[4:]
            
            questions = json.loads(result.strip())
            return questions[:5]  # Limit to 5
            
        except Exception as e:
            logger.error(f"Q&A generation error: {e}")
            return []
    
    async def _generate_summary(self, company_name: str, filing_type: str, content: str) -> str:
        """Generic summary generation (fallback)"""
        prompt = f"""Create a summary of this {filing_type} filing from {company_name}.

Content:
{content[:3000]}

Write a clear summary (300-400 words) covering the key points."""

        return await self._generate_text(prompt, max_tokens=1000)
    
    async def _generate_questions(self, company_name: str, filing_type: str, content: str) -> List[Dict]:
        """Generic question generation (fallback)"""
        prompt = f"""Generate 3-4 key questions about this {filing_type} filing from {company_name}.

Content:
{content[:2000]}

Format as JSON array."""

        return await self._generate_qa_json(prompt)
    
    def _extract_tags(self, summary: str) -> List[str]:
        """
        Generic tag extraction from summary
        """
        tags = []
        
        keyword_mapping = {
            'revenue': '#Revenue',
            'earnings': '#Earnings',
            'growth': '#Growth',
            'acquisition': '#M&A',
            'dividend': '#Dividend',
            'buyback': '#Buyback',
            'guidance': '#Guidance',
            'restructuring': '#Restructuring'
        }
        
        summary_lower = summary.lower()
        for keyword, tag in keyword_mapping.items():
            if keyword in summary_lower:
                tags.append(tag)
        
        # Ensure at least one tag
        if not tags:
            tags.append('#Update')
        
        return tags[:5]  # Limit to 5 tags


# Create singleton instance
ai_processor = AIProcessor()