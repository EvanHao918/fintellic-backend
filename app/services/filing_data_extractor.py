# app/services/filing_data_extractor.py
"""
Service for extracting structured data from filing text
"""
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup


class FilingDataExtractor:
    """Extract structured data from filing text"""
    
    # 8-K Item patterns
    ITEM_8K_PATTERNS = {
        "1.01": "Entry into a Material Definitive Agreement",
        "1.02": "Termination of a Material Definitive Agreement",
        "1.03": "Bankruptcy or Receivership",
        "2.01": "Completion of Acquisition or Disposition of Assets",
        "2.02": "Results of Operations and Financial Condition",
        "2.03": "Creation of a Direct Financial Obligation",
        "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
        "3.02": "Unregistered Sales of Equity Securities",
        "4.01": "Changes in Registrant's Certifying Accountant",
        "5.01": "Changes in Control of Registrant",
        "5.02": "Departure of Directors or Certain Officers",
        "5.03": "Amendments to Articles of Incorporation or Bylaws",
        "5.07": "Submission of Matters to a Vote of Security Holders",
        "7.01": "Regulation FD Disclosure",
        "8.01": "Other Events",
        "9.01": "Financial Statements and Exhibits"
    }
    
    def __init__(self):
        self.soup = None
        self.text = None
    
    def load_filing(self, filing_content: str):
        """Load filing content for processing"""
        self.soup = BeautifulSoup(filing_content, 'html.parser')
        self.text = self.soup.get_text()
    
    def extract_8k_items(self) -> List[Dict[str, str]]:
        """Extract 8-K items from filing"""
        items = []
        
        # Pattern to find Item sections
        item_pattern = r'Item\s+(\d+\.\d+)\s*[\.:]?\s*([^\n]+)'
        
        matches = re.finditer(item_pattern, self.text, re.IGNORECASE | re.MULTILINE)
        
        for match in matches:
            item_number = match.group(1)
            item_text = match.group(2).strip()
            
            # Clean up the item text
            item_text = re.sub(r'\s+', ' ', item_text)
            item_text = item_text.strip('.')
            
            # Get standard description if available
            standard_desc = self.ITEM_8K_PATTERNS.get(item_number)
            
            items.append({
                "item_number": item_number,
                "description": standard_desc or item_text,
                "raw_text": item_text
            })
        
        return items
    
    def extract_8k_event_timeline(self) -> Dict[str, Optional[str]]:
        """Extract event timeline from 8-K (returns ISO format strings for JSON compatibility)"""
        timeline = {
            "event_date": None,
            "filing_date": None,
            "effective_date": None
        }
        
        # Common date patterns in 8-K
        date_patterns = [
            (r'(?:on|dated?)\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})', 'event_date'),
            (r'effective\s+(?:as\s+of\s+)?([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})', 'effective_date'),
            (r'filed?\s+(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})', 'filing_date')
        ]
        
        for pattern, date_type in date_patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    # Parse various date formats
                    for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y']:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            # Convert to ISO format string for JSON serialization
                            timeline[date_type] = parsed_date.isoformat()
                            break
                        except ValueError:
                            continue
                except:
                    pass
        
        return timeline
    
    def extract_fiscal_period(self) -> Tuple[Optional[str], Optional[str]]:
        """Extract fiscal year and quarter from filing"""
        fiscal_year = None
        fiscal_quarter = None
        
        # Fiscal year pattern
        year_pattern = r'fiscal\s+year\s+(?:ended?|ending)\s+.*?(\d{4})'
        year_match = re.search(year_pattern, self.text, re.IGNORECASE)
        if year_match:
            fiscal_year = year_match.group(1)
        
        # Fiscal quarter pattern
        quarter_patterns = [
            r'(?:first|second|third|fourth)\s+quarter',
            r'Q([1-4])\s+\d{4}',
            r'quarter\s+ended?\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})'
        ]
        
        for pattern in quarter_patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                if pattern.startswith('Q'):
                    fiscal_quarter = f"Q{match.group(1)}"
                elif 'first' in match.group(0).lower():
                    fiscal_quarter = "Q1"
                elif 'second' in match.group(0).lower():
                    fiscal_quarter = "Q2"
                elif 'third' in match.group(0).lower():
                    fiscal_quarter = "Q3"
                elif 'fourth' in match.group(0).lower():
                    fiscal_quarter = "Q4"
                break
        
        # Combine quarter with year if both found
        if fiscal_quarter and fiscal_year:
            fiscal_quarter = f"{fiscal_quarter} {fiscal_year}"
        
        return fiscal_year, fiscal_quarter
    
    def extract_financial_tables(self) -> List[Dict]:
        """Extract financial data tables from filing"""
        tables = []
        
        # Find all tables in the document
        if self.soup:
            for table in self.soup.find_all('table'):
                # Check if it's a financial table
                table_text = table.get_text().lower()
                if any(keyword in table_text for keyword in ['revenue', 'income', 'assets', 'cash flow']):
                    # Extract table data
                    rows = []
                    for tr in table.find_all('tr'):
                        cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                        if cells:
                            rows.append(cells)
                    
                    if rows:
                        tables.append({
                            'headers': rows[0] if rows else [],
                            'data': rows[1:] if len(rows) > 1 else []
                        })
        
        return tables
    
    def extract_period_end_date(self) -> Optional[str]:
        """Extract period end date from filing (returns ISO format string)"""
        # Common patterns for period end date
        patterns = [
            r'period\s+ended?\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
            r'as\s+of\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
            r'for\s+the\s+(?:year|quarter)\s+ended?\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    # Try different date formats
                    for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y']:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            return parsed_date.isoformat()
                        except ValueError:
                            continue
                except:
                    pass
        
        return None
    
    def extract_auditor_opinion(self) -> Optional[str]:
        """Extract auditor opinion from 10-K"""
        # Look for auditor opinion section
        opinion_patterns = [
            r'opinion\s+on\s+the\s+financial\s+statements(.*?)(?:critical\s+audit|basis\s+for)',
            r'report\s+of\s+independent.*?auditors?(.*?)(?:critical\s+audit|basis\s+for)',
            r'we\s+have\s+audited(.*?)(?:in\s+our\s+opinion|we\s+believe)'
        ]
        
        for pattern in opinion_patterns:
            match = re.search(pattern, self.text, re.IGNORECASE | re.DOTALL)
            if match:
                opinion_text = match.group(1).strip()
                # Clean up the text
                opinion_text = re.sub(r'\s+', ' ', opinion_text)
                return opinion_text[:1000]  # Limit length
        
        return None


# Usage example
def process_filing_data(filing_type: str, filing_content: str) -> Dict:
    """Process filing content and extract structured data"""
    extractor = FilingDataExtractor()
    extractor.load_filing(filing_content)
    
    extracted_data = {}
    
    # Common extractions
    fiscal_year, fiscal_quarter = extractor.extract_fiscal_period()
    period_end_date = extractor.extract_period_end_date()
    
    extracted_data['fiscal_year'] = fiscal_year
    extracted_data['fiscal_quarter'] = fiscal_quarter
    extracted_data['period_end_date'] = period_end_date
    
    # Type-specific extractions
    if filing_type == "8-K":
        items = extractor.extract_8k_items()
        timeline = extractor.extract_8k_event_timeline()
        
        extracted_data['items'] = items
        extracted_data['item_type'] = items[0]['item_number'] if items else None
        extracted_data['event_timeline'] = timeline
        
        # Determine event type from items
        if items:
            first_item = items[0]['item_number']
            extracted_data['event_type'] = extractor.ITEM_8K_PATTERNS.get(first_item, "Other Event")
    
    elif filing_type == "10-K":
        extracted_data['auditor_opinion'] = extractor.extract_auditor_opinion()
        # Note: More complex extractions like business segments would require
        # more sophisticated parsing or external data sources
    
    elif filing_type == "10-Q":
        # Extract financial tables for quarterly analysis
        tables = extractor.extract_financial_tables()
        if tables:
            extracted_data['financial_tables'] = tables
    
    return extracted_data