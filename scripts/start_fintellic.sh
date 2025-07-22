#!/bin/bash

# Fintellic Backend Startup Script - Fixed Version
# Optimized for macOS with Celery thread pool

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"
DATA_DIR="$PROJECT_DIR/data/filings"

# Create necessary directories
mkdir -p "$LOG_DIR"
mkdir -p "$PID_DIR"
mkdir -p "$DATA_DIR"

# Fix macOS fork issue for Celery
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

echo -e "${BLUE}========================================"
echo "   Starting Fintellic Backend Services"
echo -e "========================================${NC}"

# Function to check if a service is running
check_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  $service_name is already running (PID: $pid)${NC}"
            return 0
        else
            rm -f "$pid_file"
        fi
    fi
    return 1
}

# Function to start a service
start_service() {
    local service_name=$1
    local command=$2
    local pid_file=$3
    local log_file=$4
    
    echo -e "${BLUE}Starting $service_name...${NC}"
    nohup $command > "$log_file" 2>&1 &
    local pid=$!
    echo $pid > "$pid_file"
    
    sleep 2
    
    if ps -p $pid > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name started successfully (PID: $pid)${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed to start $service_name${NC}"
        rm -f "$pid_file"
        return 1
    fi
}

# 1. Check PostgreSQL
echo -e "${BLUE}Checking PostgreSQL...${NC}"
if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PostgreSQL is running${NC}"
else
    echo -e "${RED}❌ PostgreSQL is not running${NC}"
    echo "Please start PostgreSQL first:"
    echo "  brew services start postgresql@14"
    exit 1
fi

# 2. Check Redis
echo -e "${BLUE}Checking Redis...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis is running${NC}"
    cache_keys=$(redis-cli dbsize | awk '{print $2}')
    echo -e "${CYAN}   Cache keys: ${cache_keys}${NC}"
else
    echo -e "${YELLOW}Starting Redis...${NC}"
    if command -v redis-server > /dev/null; then
        redis-server --daemonize yes --logfile "$LOG_DIR/redis.log"
        sleep 2
        if redis-cli ping > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Redis started${NC}"
        else
            echo -e "${RED}❌ Failed to start Redis${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ Redis not installed. Install with: brew install redis${NC}"
        exit 1
    fi
fi

# 3. Database Health Check
echo -e "${BLUE}Checking database health...${NC}"
python -c "
from app.core.database import SessionLocal
from app.models import Company, Filing
from sqlalchemy import text

try:
    db = SessionLocal()
    # Test connection
    db.execute(text('SELECT 1'))
    
    # Check data
    companies = db.query(Company).count()
    filings = db.query(Filing).count()
    
    print(f'  Companies: {companies}')
    print(f'  Filings: {filings}')
    
    if companies == 0:
        print('⚠️  No companies in database. Run: python scripts/fetch_sp500.py')
    
    db.close()
except Exception as e:
    print(f'❌ Database error: {e}')
    exit(1)
"

# 4. Check Python environment
echo -e "${BLUE}Verifying Python environment...${NC}"
python -c "
import sys
modules = ['fastapi', 'celery', 'redis', 'sqlalchemy', 'openai']
missing = []
for module in modules:
    try:
        __import__(module)
    except ImportError:
        missing.append(module)

if missing:
    print(f'❌ Missing modules: {missing}')
    sys.exit(1)
else:
    print('✅ All required modules installed')
"

# 5. Check OpenAI API Key
echo -e "${BLUE}Checking API configuration...${NC}"
python -c "
from app.core.config import settings
if settings.OPENAI_API_KEY:
    print('✅ OpenAI API Key configured')
else:
    print('⚠️  OpenAI API Key not set (AI analysis will fail)')
"

# 6. Start Celery Worker (Fixed for macOS)
if ! check_service "Celery Worker" "$PID_DIR/celery.pid"; then
    echo -e "${BLUE}Starting Celery Worker...${NC}"
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Start Celery with thread pool to avoid macOS fork issues
    celery -A app.core.celery_app worker \
        --loglevel=info \
        --pool=threads \
        --concurrency=4 \
        > "$LOG_DIR/celery.log" 2>&1 &
    
    CELERY_PID=$!
    echo $CELERY_PID > "$PID_DIR/celery.pid"
    
    sleep 3
    
    if ps -p $CELERY_PID > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Celery Worker started successfully (PID: $CELERY_PID)${NC}"
        
        # Check if worker is actually ready
        if grep -q "celery@" "$LOG_DIR/celery.log" 2>/dev/null; then
            echo -e "${GREEN}   Worker is ready and accepting tasks${NC}"
        fi
    else
        echo -e "${RED}❌ Failed to start Celery Worker${NC}"
        echo "Check logs at: $LOG_DIR/celery.log"
        rm -f "$PID_DIR/celery.pid"
    fi
fi

# 7. Start FastAPI Server (with integrated scheduler)
if ! check_service "FastAPI Server" "$PID_DIR/fastapi.pid"; then
    start_service "FastAPI Server" \
        "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1" \
        "$PID_DIR/fastapi.pid" \
        "$LOG_DIR/fastapi.log"
fi

# 8. Health check
echo -e "${BLUE}Performing system health check...${NC}"
sleep 3

# Check API endpoint
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ API is responding${NC}"
else
    echo -e "${RED}❌ API is not responding${NC}"
fi

# Check Celery worker status
if [ -f "$PID_DIR/celery.pid" ]; then
    CELERY_PID=$(cat "$PID_DIR/celery.pid")
    if ps -p $CELERY_PID > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Celery Worker is running${NC}"
    else
        echo -e "${RED}❌ Celery Worker is not running${NC}"
    fi
fi

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Fintellic Backend is Running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "📊 Service Status:"
echo "   - API: http://localhost:8000"
echo "   - Docs: http://localhost:8000/docs"
echo "   - Health: http://localhost:8000/health"
echo ""
echo "🚀 Features:"
echo "   - Auto-scanning every minute"
echo "   - Redis caching enabled"
echo "   - S&P 500 + NASDAQ 100 monitoring"
echo "   - Thread pool for macOS compatibility"
echo ""
echo "📁 Locations:"
echo "   - Logs: $LOG_DIR/"
echo "   - Data: $DATA_DIR/"
echo "   - PIDs: $PID_DIR/"
echo ""
echo "🛠️ Useful Commands:"
echo "   - Monitor: python scripts/check_filing_status.py"
echo "   - Stop: ./scripts/stop_fintellic.sh"
echo "   - Trigger scan: curl -X POST http://localhost:8000/api/v1/scan/trigger"
echo "   - View logs: tail -f $LOG_DIR/celery.log"
echo ""

# Show recent activity
echo -e "${CYAN}📈 Recent Activity:${NC}"
recent_filings=$(find "$DATA_DIR" -type f -name "*.htm*" -mtime -1 2>/dev/null | wc -l | tr -d ' ')
echo "   - New filings (24h): $recent_filings"

# Show pending tasks
if command -v redis-cli > /dev/null 2>&1; then
    pending_tasks=$(redis-cli llen celery 2>/dev/null || echo "0")
    echo "   - Pending tasks: $pending_tasks"
fi

echo ""
echo -e "${CYAN}💡 Note: Using thread pool for Celery to avoid macOS fork issues${NC}"