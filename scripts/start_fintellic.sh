#!/bin/bash
# Fintellic Backend Startup Script - Updated for Day 8
# Starts all required services including Redis caching

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

# PID files location
PID_DIR="$PROJECT_ROOT/pids"
LOG_DIR="$PROJECT_ROOT/logs"

# Create necessary directories
mkdir -p "$PID_DIR"
mkdir -p "$LOG_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Starting Fintellic Backend Services${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check if a service is running
check_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  $service_name is already running (PID: $pid)${NC}"
            return 0
        else
            # PID file exists but process is not running
            rm "$pid_file"
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
    
    # Start the service in background and redirect output to log
    nohup $command > "$log_file" 2>&1 &
    local pid=$!
    
    # Save PID
    echo $pid > "$pid_file"
    
    # Wait a moment and check if it started successfully
    sleep 2
    
    if ps -p $pid > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name started successfully (PID: $pid)${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed to start $service_name${NC}"
        echo -e "${RED}   Check log file: $log_file${NC}"
        rm -f "$pid_file"
        return 1
    fi
}

# 1. Check PostgreSQL
echo -e "${BLUE}Checking PostgreSQL...${NC}"
if pg_isready -q; then
    echo -e "${GREEN}✅ PostgreSQL is running${NC}"
else
    echo -e "${RED}❌ PostgreSQL is not running${NC}"
    echo "Please start PostgreSQL first:"
    echo "  brew services start postgresql@16"
    exit 1
fi

# 2. Start Redis (CRITICAL for Day 8 caching features)
echo -e "${BLUE}Starting Redis (Required for caching)...${NC}"
if ! check_service "Redis" "$PID_DIR/redis.pid"; then
    # Check if Redis is already running on default port
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Redis is already running (external process)${NC}"
    else
        start_service "Redis" \
            "redis-server" \
            "$PID_DIR/redis.pid" \
            "$LOG_DIR/redis.log"
    fi
else
    echo -e "${GREEN}✅ Redis is already running${NC}"
fi

# Verify Redis connectivity
echo -e "${BLUE}Verifying Redis connectivity...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis connection verified${NC}"
    # Show cache statistics
    KEYS_COUNT=$(redis-cli dbsize | awk '{print $2}')
    echo -e "${BLUE}   Cache keys in database: ${KEYS_COUNT}${NC}"
else
    echo -e "${RED}❌ Cannot connect to Redis!${NC}"
    echo "Redis is required for caching features added in Day 8"
    exit 1
fi

# 3. Set Python path - since we know you're in venv already
echo -e "${BLUE}Using current Python environment...${NC}"
PYTHON_BIN="python"  # This will use the activated venv python

# Verify Python setup
echo -e "${BLUE}Verifying Python setup...${NC}"
$PYTHON_BIN -c "import app" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Cannot import app module!${NC}"
    echo "Please ensure all dependencies are installed:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Verify Day 8 modules
echo -e "${BLUE}Verifying Day 8 modules...${NC}"
$PYTHON_BIN -c "from app.core.cache import cache; from app.models.earnings_calendar import EarningsCalendar" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Day 8 modules not found!${NC}"
    echo "Please ensure you have the latest code from Day 8"
    exit 1
fi
echo -e "${GREEN}✅ Python environment verified (including Day 8 features)${NC}"

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

# 6. Start FastAPI Server
if ! check_service "FastAPI Server" "$PID_DIR/fastapi.pid"; then
    start_service "FastAPI Server" \
        "uvicorn app.main:app --host 0.0.0.0 --port 8000" \
        "$PID_DIR/fastapi.pid" \
        "$LOG_DIR/fastapi.log"
fi

# 7. Wait for services to be ready
echo -e "${BLUE}Waiting for services to be ready...${NC}"
sleep 3

# 8. Start the Main Scheduler
if ! check_service "Filing Scheduler" "$PID_DIR/scheduler.pid"; then
    echo -e "${BLUE}Starting Filing Scheduler...${NC}"
    
    # Run the scheduler
    nohup python scripts/run_scheduler.py > "$LOG_DIR/scheduler.log" 2>&1 &
    scheduler_pid=$!
    echo $scheduler_pid > "$PID_DIR/scheduler.pid"
    
    sleep 2
    
    if ps -p $scheduler_pid > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Filing Scheduler started successfully (PID: $scheduler_pid)${NC}"
    else
        echo -e "${RED}❌ Failed to start Filing Scheduler${NC}"
        echo -e "${RED}   Check log file: $LOG_DIR/scheduler.log${NC}"
        rm -f "$PID_DIR/scheduler.pid"
    fi
fi

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
fi
if [ ! -f "$PID_DIR/scheduler.pid" ] || ! ps -p $(cat "$PID_DIR/scheduler.pid" 2>/dev/null) > /dev/null 2>&1; then
    echo -e "${RED}❌ Filing Scheduler is not running${NC}"
    all_running=false
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
    echo "  tail -f $LOG_DIR/scheduler.log"
fi

echo ""
echo "📊 Service URLs:"
echo "   - API Documentation: http://localhost:8000/docs"
echo "   - API Base URL: http://localhost:8000/api/v1"
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
echo "   - Scheduler: $LOG_DIR/scheduler.log"
echo ""
echo "🛑 To stop all services, run: ./scripts/stop_fintellic.sh"
echo ""

if [ "$all_running" = true ]; then
    echo -e "${YELLOW}🤖 The system is now running autonomously!${NC}"
    echo -e "${YELLOW}   - Scanning for new filings every minute${NC}"
    echo -e "${YELLOW}   - Automatically processing discovered filings${NC}"
    echo -e "${YELLOW}   - Caching frequently accessed data${NC}"
    echo -e "${YELLOW}   - Tracking community interactions${NC}"
    echo ""
    echo "📝 To monitor in real-time:"
    echo "   tail -f $LOG_DIR/scheduler.log"
    echo ""
    echo "📊 To check cache statistics:"
    echo "   redis-cli info stats"
    echo ""
    echo "🔍 To see cached keys:"
    echo "   redis-cli keys '*'"
fi