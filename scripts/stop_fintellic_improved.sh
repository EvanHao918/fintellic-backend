#!/bin/bash
# Fintellic Backend Stop Script - Improved Version
# Gracefully stops all services and cleans up

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
PID_DIR="$PROJECT_DIR/pids"
LOG_DIR="$PROJECT_DIR/logs"

echo -e "${BLUE}========================================"
echo "   Stopping Fintellic Backend Services"
echo -e "========================================${NC}"

# Function to stop a service gracefully
stop_service() {
    local service_name=$1
    local pid_file=$2
    local force=$3
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${BLUE}Stopping $service_name (PID: $pid)...${NC}"
            
            # Try graceful shutdown first
            kill -TERM "$pid" 2>/dev/null
            
            # Wait up to 10 seconds for graceful shutdown
            local count=0
            while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            
            # Force kill if still running and force flag is set
            if ps -p "$pid" > /dev/null 2>&1; then
                if [ "$force" = "force" ]; then
                    echo -e "${YELLOW}Force stopping $service_name...${NC}"
                    kill -9 "$pid" 2>/dev/null
                    sleep 1
                else
                    echo -e "${YELLOW}⚠️  $service_name is still running. Use --force to force stop${NC}"
                    return 1
                fi
            fi
            
            echo -e "${GREEN}✅ $service_name stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  $service_name was not running (stale PID file)${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️  $service_name was not running (no PID file)${NC}"
    fi
    return 0
}

# Check for force flag
FORCE_STOP=""
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE_STOP="force"
    echo -e "${YELLOW}Force stop mode enabled${NC}"
fi

# 1. Stop FastAPI Server (includes integrated scheduler)
stop_service "FastAPI Server" "$PID_DIR/fastapi.pid" "$FORCE_STOP"

# 2. Stop Celery Worker
stop_service "Celery Worker" "$PID_DIR/celery.pid" "$FORCE_STOP"

# 3. Stop Celery Beat (if running)
if [ -f "$PID_DIR/celery-beat.pid" ]; then
    stop_service "Celery Beat" "$PID_DIR/celery-beat.pid" "$FORCE_STOP"
fi

# 4. Check Redis (but don't stop if it's a system service)
echo -e "${BLUE}Checking Redis...${NC}"
if [ -f "$PID_DIR/redis.pid" ]; then
    # We started Redis, so we should stop it
    stop_service "Redis" "$PID_DIR/redis.pid" "$FORCE_STOP"
else
    # Redis is managed externally
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${CYAN}ℹ️  Redis is running (system service) - not stopping${NC}"
    fi
fi

# 5. Clean up any orphaned processes
echo -e "${BLUE}Checking for orphaned processes...${NC}"
orphaned=$(ps aux | grep -E "(celery|uvicorn|fastapi)" | grep -v grep | grep -v stop_fintellic)
if [ ! -z "$orphaned" ]; then
    echo -e "${YELLOW}Found orphaned processes:${NC}"
    echo "$orphaned"
    if [ "$FORCE_STOP" = "force" ]; then
        echo -e "${YELLOW}Killing orphaned processes...${NC}"
        pkill -f "celery.*fintellic" 2>/dev/null
        pkill -f "uvicorn.*app.main" 2>/dev/null
    else
        echo -e "${YELLOW}Use --force to kill orphaned processes${NC}"
    fi
fi

# 6. Show service status
echo ""
echo -e "${BLUE}Service Status:${NC}"

# Check what's still running
still_running=false
if pgrep -f "uvicorn.*app.main" > /dev/null; then
    echo -e "${RED}❌ FastAPI is still running${NC}"
    still_running=true
else
    echo -e "${GREEN}✅ FastAPI is stopped${NC}"
fi

if pgrep -f "celery.*worker" > /dev/null; then
    echo -e "${RED}❌ Celery Worker is still running${NC}"
    still_running=true
else
    echo -e "${GREEN}✅ Celery Worker is stopped${NC}"
fi

# 7. Optional cleanup
if [ "$2" = "--clean" ]; then
    echo ""
    echo -e "${BLUE}Performing cleanup...${NC}"
    
    # Rotate logs
    if [ -d "$LOG_DIR" ]; then
        for log in "$LOG_DIR"/*.log; do
            if [ -f "$log" ] && [ -s "$log" ]; then
                mv "$log" "${log}.$(date +%Y%m%d_%H%M%S)"
                echo -e "${GREEN}✅ Rotated $(basename $log)${NC}"
            fi
        done
    fi
    
    # Clear Redis cache (optional)
    read -p "Clear Redis cache? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        redis-cli FLUSHDB > /dev/null 2>&1
        echo -e "${GREEN}✅ Redis cache cleared${NC}"
    fi
fi

# Summary
echo ""
if [ "$still_running" = true ]; then
    echo -e "${YELLOW}========================================"
    echo "   Some Services Still Running"
    echo -e "========================================${NC}"
    echo "Use: $0 --force to force stop all services"
else
    echo -e "${GREEN}========================================"
    echo "   All Services Stopped"
    echo -e "========================================${NC}"
fi

echo ""
echo "📝 Options:"
echo "   --force    Force stop all services"
echo "   --clean    Rotate logs and optionally clear cache"
echo ""
echo "🚀 To restart services:"
echo "   ./scripts/start_fintellic.sh"
echo ""
echo "📊 To check system status:"
echo "   python system_health_check.py"

