#!/usr/bin/env python3
"""
Add test filings using raw SQL to avoid model import issues
"""
import psycopg2
from datetime import datetime, timedelta
import json

# Database connection
conn = psycopg2.connect(
    host="localhost",
    database="fintellic_db",
    user="fintellic_user",
    password="fintellic123"  # Update with your password
)

def add_test_filings_sql():
    cur = conn.cursor()
    
    try:
        # Check existing completed filings
        cur.execute("SELECT COUNT(*) FROM filings WHERE status = 'COMPLETED'")
        existing_count = cur.fetchone()[0]
        print(f"Existing completed filings: {existing_count}")
        
        # Get company ID 5
        cur.execute("SELECT id, name, ticker FROM companies WHERE id = 5")
        company = cur.fetchone()
        if not company:
            # Get any company
            cur.execute("SELECT id, name, ticker FROM companies LIMIT 1")
            company = cur.fetchone()
        
        if not company:
            print("No companies found!")
            return
            
        company_id, company_name, ticker = company
        print(f"Using company: {company_name} ({ticker})")
        
        # Add test filings
        filings_to_add = max(0, 5 - existing_count)
        
        if filings_to_add == 0:
            print("Already have enough test filings")
            return
            
        print(f"Adding {filings_to_add} test filings...")
        
        filing_types = ['FORM_10K', 'FORM_10Q', 'FORM_8K']
        tones = ['OPTIMISTIC', 'CONFIDENT', 'NEUTRAL']
        
        for i in range(filings_to_add):
            filing_type = filing_types[i % len(filing_types)]
            tone = tones[i % len(tones)]
            now = datetime.utcnow()
            
            accession = f"TEST-{int(now.timestamp())}-{i}"
            filing_date = now - timedelta(days=i)
            period_date = now - timedelta(days=30+i)
            
            ai_summary = f"""This is a test {filing_type} filing for {company_name}. 

Key highlights:
- Revenue increased by {15 + i}% year-over-year
- Operating margin improved to {20 + i}%
- Strong growth in cloud services division
- International expansion showing positive results

Management remains optimistic about future growth prospects."""

            key_tags = json.dumps(["Growth", "Revenue", "Expansion"])
            key_questions = json.dumps([
                {"question": "What drove revenue growth?", "answer": "Strong demand in cloud services"},
                {"question": "What are the growth prospects?", "answer": "Continued double-digit growth expected"}
            ])
            
            sql = """
            INSERT INTO filings (
                company_id, accession_number, filing_type, filing_date, period_date,
                primary_doc_url, primary_doc_description, ai_summary, management_tone,
                tone_explanation, key_tags, key_questions, status, 
                processing_completed_at, bullish_votes, neutral_votes, bearish_votes,
                comment_count, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            values = (
                company_id, accession, filing_type, filing_date, period_date,
                f"https://example.com/test-{i}.htm", f"Test {filing_type}",
                ai_summary, tone, "Management expressed confidence",
                key_tags, key_questions, 'COMPLETED',
                now, 10 + i*2, 5, 2, i, now
            )
            
            cur.execute(sql, values)
            print(f"Added test {filing_type}")
        
        conn.commit()
        print(f"\n✅ Successfully added {filings_to_add} test filings")
        
        # Show all completed filings
        cur.execute("""
            SELECT id, filing_type, c.name 
            FROM filings f 
            JOIN companies c ON f.company_id = c.id 
            WHERE f.status = 'COMPLETED' 
            ORDER BY f.id
        """)
        
        print("\nAll completed filings:")
        for row in cur.fetchall():
            print(f"  ID: {row[0]}, Type: {row[1]}, Company: {row[2]}")
            
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cur.close()

if __name__ == "__main__":
    add_test_filings_sql()
    conn.close()