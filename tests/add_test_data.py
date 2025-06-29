"""
Script to add test data to the database
Run this from the project root directory
"""
import sys
sys.path.append('.')

from datetime import datetime, timedelta
from app.core.database import SessionLocal
from app.models.company import Company
from app.models.filing import Filing, ProcessingStatus
import random

def add_test_data():
    db = SessionLocal()
    
    try:
        # Check if we already have test data
        existing_companies = db.query(Company).count()
        if existing_companies > 0:
            print(f"Database already has {existing_companies} companies")
            response = input("Do you want to add more test data? (y/n): ")
            if response.lower() != 'y':
                return
        
        # Add some test companies
        test_companies = [
            {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193", "sector": "Technology"},
            {"ticker": "MSFT", "name": "Microsoft Corporation", "cik": "0000789019", "sector": "Technology"},
            {"ticker": "GOOGL", "name": "Alphabet Inc.", "cik": "0001652044", "sector": "Technology"},
            {"ticker": "AMZN", "name": "Amazon.com Inc.", "cik": "0001018724", "sector": "Consumer Discretionary"},
            {"ticker": "TSLA", "name": "Tesla Inc.", "cik": "0001318605", "sector": "Consumer Discretionary"},
        ]
        
        for company_data in test_companies:
            # Check if company already exists
            existing = db.query(Company).filter(Company.ticker == company_data["ticker"]).first()
            if not existing:
                company = Company(**company_data)
                db.add(company)
                print(f"Added company: {company.ticker}")
            else:
                print(f"Company already exists: {existing.ticker}")
        
        db.commit()
        
        # Add some test filings
        companies = db.query(Company).all()
        form_types = ["10-K", "10-Q", "8-K"]
        sentiments = ["bullish", "neutral", "bearish"]
        
        for company in companies:
            # Add 3-5 filings per company
            num_filings = random.randint(3, 5)
            
            for i in range(num_filings):
                filing_date = datetime.now() - timedelta(days=random.randint(1, 90))
                form_type = random.choice(form_types)
                
                filing = Filing(
                    cik=company.cik,
                    form_type=form_type,
                    filing_date=filing_date,
                    accession_number=f"0000{company.cik}-25-{str(i+1).zfill(6)}",
                    file_url=f"https://www.sec.gov/Archives/edgar/data/{company.cik}/test-{i+1}.htm",
                    company_name=company.name,
                    status=ProcessingStatus.COMPLETED,
                    
                    # AI-generated content (mock data)
                    ai_summary=f"This is a test {form_type} filing for {company.name}. "
                              f"The company reported strong performance in key areas. "
                              f"Management remains optimistic about future growth prospects.",
                    
                    one_liner=f"{company.ticker} reports solid quarterly results with growth in key segments",
                    sentiment=random.choice(sentiments),
                    sentiment_explanation="Based on positive revenue growth and optimistic management commentary",
                    
                    key_points=[
                        "Revenue increased 15% year-over-year",
                        "Operating margins improved by 200 basis points",
                        "Strong cash flow generation"
                    ],
                    
                    risks=[
                        "Supply chain disruptions",
                        "Increased competition",
                        "Regulatory uncertainty"
                    ],
                    
                    opportunities=[
                        "Expansion into new markets",
                        "AI integration opportunities",
                        "Cost optimization initiatives"
                    ],
                    
                    questions_answers=[
                        {
                            "question": "What drove revenue growth this quarter?",
                            "answer": "Strong demand for cloud services and AI products"
                        },
                        {
                            "question": "How is the company addressing supply chain issues?",
                            "answer": "Diversifying suppliers and increasing inventory buffers"
                        }
                    ],
                    
                    tags=["growth", "earnings", "technology", "AI"],
                    
                    processed_at=filing_date + timedelta(minutes=5)
                )
                
                # Add financial metrics for 10-K and 10-Q
                if form_type in ["10-K", "10-Q"]:
                    filing.financial_metrics = {
                        "revenue": f"${random.randint(50, 200)}B",
                        "net_income": f"${random.randint(10, 50)}B",
                        "eps": f"${random.uniform(2, 10):.2f}",
                        "total_assets": f"${random.randint(200, 500)}B"
                    }
                
                db.add(filing)
            
            print(f"Added {num_filings} filings for {company.ticker}")
        
        db.commit()
        print("\nTest data added successfully!")
        
        # Show summary
        total_companies = db.query(Company).count()
        total_filings = db.query(Filing).count()
        print(f"\nDatabase now contains:")
        print(f"- {total_companies} companies")
        print(f"- {total_filings} filings")
        
    except Exception as e:
        print(f"Error adding test data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("Adding test data to Fintellic database...")
    add_test_data()