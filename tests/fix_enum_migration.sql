-- fix_enum_migration.sql
-- Clean solution: recreate enum with uppercase values to match Python

-- 1. Drop existing table and enum
DROP TABLE IF EXISTS earnings_calendar CASCADE;
DROP TYPE IF EXISTS earningstime CASCADE;

-- 2. Create enum with uppercase values
CREATE TYPE earningstime AS ENUM ('BMO', 'AMC', 'TNS');

-- 3. Recreate table with correct enum
CREATE TABLE earnings_calendar (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    earnings_date DATE NOT NULL,
    earnings_time earningstime DEFAULT 'TNS',
    fiscal_quarter VARCHAR(10),
    fiscal_year INTEGER,
    eps_estimate FLOAT,
    revenue_estimate FLOAT,
    previous_eps FLOAT,
    previous_revenue FLOAT,
    is_confirmed BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'yfinance',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create indexes
CREATE INDEX ix_earnings_calendar_company_id ON earnings_calendar(company_id);
CREATE INDEX ix_earnings_calendar_earnings_date ON earnings_calendar(earnings_date);

-- 5. Verify enum values
SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'earningstime');