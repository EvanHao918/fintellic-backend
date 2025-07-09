#!/bin/bash
# Fintellic Backend Stop Script
# Stops all running services

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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Stopping Fintellic Backend Services${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to stop a service
stop_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${BLUE}Stopping $service_name (PID: $pid)...${NC}"
            kill -15 "$pid"
            
            # Wait for graceful shutdown
            sleep 2
            
            # Force kill if still running
            if ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${YELLOW}Force stopping $service_name...${NC}"
                kill -9 "$pid"
            fi
            
            echo -e "${GREEN}✅ $service_name stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  $service_name was not running (stale PID file)${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️  $service_name was not running (no PID file)${NC}"
    fi
}

# Stop all services
stop_service "Filing Scheduler" "$PID_DIR/scheduler.pid"
stop_service "FastAPI Server" "$PID_DIR/fastapi.pid"
stop_service "Celery Beat" "$PID_DIR/celery-beat.pid"
stop_service "Celery Worker" "$PID_DIR/celery.pid"
stop_service "Redis" "$PID_DIR/redis.pid"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   All Services Stopped${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "To restart services, run: ./scripts/start_fintellic.sh"