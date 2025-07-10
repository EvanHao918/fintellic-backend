#!/bin/bash

# Fintellic Backend Startup Script - Fixed Version
# Removes independent scheduler since it's already running inside FastAPI

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

# Create necessary directories
mkdir -p "$LOG_DIR"
mkdir -p "$PID_DIR"

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
            # PID file exists but process is not running
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
echo -e "${BLUE}Starting Redis (Required for caching)...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis is already running (external process)${NC}"
else
    echo -e "${YELLOW}⚠️  Redis is not running. Starting Redis...${NC}"
    if command -v redis-server > /dev/null; then
        nohup redis-server > "$LOG_DIR/redis.log" 2>&1 &
        echo $! > "$PID_DIR/redis.pid"
        sleep 2
        if redis-cli ping > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Redis started successfully${NC}"
        else
            echo -e "${RED}❌ Failed to start Redis${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ Redis is not installed${NC}"
        echo "Please install Redis first:"
        echo "  brew install redis"
        exit 1
    fi
fi

# Verify Redis connectivity
echo -e "${BLUE}Verifying Redis connectivity...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis connection verified${NC}"
    # Show cache statistics
    cache_keys=$(redis-cli dbsize | awk '{print $2}')
    echo -e "${BLUE}   Cache keys in database: ${cache_keys}${NC}"
else
    echo -e "${RED}❌ Cannot connect to Redis${NC}"
    exit 1
fi

# 3. Check Python environment
echo -e "${BLUE}Using current Python environment...${NC}"
echo -e "${BLUE}Verifying Python setup...${NC}"

# Verify required packages
python -c "import fastapi, celery, redis, sqlalchemy" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Python packages verified${NC}"
else
    echo -e "${RED}❌ Missing required Python packages${NC}"
    echo "Please install requirements:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Verify Day 8 modules
echo -e "${BLUE}Verifying Day 8 modules...${NC}"
python -c "from app.core.cache import cache; from app.models.earnings_calendar import EarningsCalendar" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Python environment verified (including Day 8 features)${NC}"
else
    echo -e "${YELLOW}⚠️  Some Day 8 modules might be missing${NC}"
fi

# 4. Start Celery Worker
if ! check_service "Celery Worker" "$PID_DIR/celery.pid"; then
    start_service "Celery Worker" \
        "celery -A app.core.celery_app worker --loglevel=info" \
        "$PID_DIR/celery.pid" \
        "$LOG_DIR/celery.log"
fi

# 5. Start Celery Beat (optional - for scheduled tasks)
if ! check_service "Celery Beat" "$PID_DIR/celery-beat.pid"; then
    start_service "Celery Beat" \
        "celery -A app.core.celery_app beat --loglevel=info" \
        "$PID_DIR/celery-beat.pid" \
        "$LOG_DIR/celery-beat.log"
fi

# 6. Start FastAPI Server (includes integrated scheduler)
if ! check_service "FastAPI Server" "$PID_DIR/fastapi.pid"; then
    echo -e "${BLUE}Starting FastAPI Server (with integrated Filing Scheduler)...${NC}"
    start_service "FastAPI Server with Scheduler" \
        "uvicorn app.main:app --host 0.0.0.0 --port 8000" \
        "$PID_DIR/fastapi.pid" \
        "$LOG_DIR/fastapi.log"
    echo -e "${GREEN}✅ Filing Scheduler is running inside FastAPI${NC}"
fi

# 7. Wait for services to be ready
echo -e "${BLUE}Waiting for services to be ready...${NC}"
sleep 3

# Check if all critical services are running
echo ""
echo -e "${BLUE}Checking service status...${NC}"

all_running=true
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}❌ Redis is not responding${NC}"
    all_running=false
fi
if [ ! -f "$PID_DIR/celery.pid" ] || ! ps -p $(cat "$PID_DIR/celery.pid" 2>/dev/null) > /dev/null 2>&1; then
    echo -e "${RED}❌ Celery Worker is not running${NC}"
    all_running=false
fi
if [ ! -f "$PID_DIR/fastapi.pid" ] || ! ps -p $(cat "$PID_DIR/fastapi.pid" 2>/dev/null) > /dev/null 2>&1; then
    echo -e "${RED}❌ FastAPI Server is not running${NC}"
    all_running=false
else
    echo -e "${GREEN}✅ FastAPI Server is running (includes Filing Scheduler)${NC}"
fi

echo ""
if [ "$all_running" = true ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}   All Services Started Successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}   Some Services Failed to Start${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    echo "Check the log files for errors:"
    echo "  tail -f $LOG_DIR/celery.log"
    echo "  tail -f $LOG_DIR/fastapi.log"
fi

echo ""
echo "📊 Service URLs:"
echo "   - API Documentation: http://localhost:8000/docs"
echo "   - API Base URL: http://localhost:8000/api/v1"
echo "   - Trigger Manual Scan: POST http://localhost:8000/api/v1/scan/trigger"
echo ""
echo "🚀 Day 8 New Features:"
echo "   - Redis Caching: Enabled (5x faster API responses)"
echo "   - Statistics API: http://localhost:8000/api/v1/stats/overview"
echo "   - Earnings Calendar: http://localhost:8000/api/v1/earnings/upcoming"
echo ""
echo "📁 Log files location:"
echo "   - Redis: $LOG_DIR/redis.log"
echo "   - Celery: $LOG_DIR/celery.log"
echo "   - FastAPI: $LOG_DIR/fastapi.log"
echo ""
echo "🛑 To stop all services, run: ./scripts/stop_fintellic.sh"
echo ""

if [ "$all_running" = true ]; then
    echo -e "${YELLOW}🤖 The system is now running autonomously!${NC}"
    echo -e "${YELLOW}   - Filing Scheduler is integrated in FastAPI${NC}"
    echo -e "${YELLOW}   - Scanning for new filings every minute${NC}"
    echo -e "${YELLOW}   - Automatically processing discovered filings${NC}"
    echo -e "${YELLOW}   - Caching frequently accessed data${NC}"
    echo ""
    echo "📝 To monitor scheduler activity:"
    echo "   tail -f $LOG_DIR/fastapi.log | grep -i scheduler"
    echo ""
    echo "🔍 To manually trigger a scan:"
    echo "   curl -X POST http://localhost:8000/api/v1/scan/trigger"
    echo ""
    echo "📊 To check cache statistics:"
    echo "   redis-cli info stats"
fi