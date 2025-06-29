#!/bin/bash
# Fintellic Backend Shutdown Script
# Stops all Fintellic backend services gracefully

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
            
            # Try graceful shutdown first (SIGTERM)
            kill -TERM "$pid" 2>/dev/null
            
            # Wait up to 10 seconds for graceful shutdown
            local count=0
            while [ $count -lt 10 ] && ps -p "$pid" > /dev/null 2>&1; do
                sleep 1
                count=$((count + 1))
                echo -n "."
            done
            echo ""
            
            # If still running, force kill
            if ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${YELLOW}Force killing $service_name...${NC}"
                kill -KILL "$pid" 2>/dev/null
                sleep 1
            fi
            
            echo -e "${GREEN}✅ $service_name stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  $service_name was not running (stale PID file)${NC}"
        fi
        
        # Remove PID file
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️  $service_name is not running (no PID file)${NC}"
    fi
}

# Stop services in reverse order of startup

# 1. Stop Filing Scheduler first (it's the main loop)
stop_service "Filing Scheduler" "$PID_DIR/scheduler.pid"

# 2. Stop FastAPI Server
stop_service "FastAPI Server" "$PID_DIR/fastapi.pid"

# 3. Stop Celery Beat
stop_service "Celery Beat" "$PID_DIR/celery-beat.pid"

# 4. Stop Celery Worker
stop_service "Celery Worker" "$PID_DIR/celery.pid"

# 5. Stop Redis (optional - you might want to keep it running)
echo -e "${BLUE}Do you want to stop Redis? (y/N)${NC}"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    stop_service "Redis" "$PID_DIR/redis.pid"
    
    # Alternative method if PID file is missing
    if command -v redis-cli &> /dev/null; then
        echo -e "${BLUE}Sending shutdown command to Redis...${NC}"
        redis-cli shutdown 2>/dev/null || true
    fi
else
    echo -e "${YELLOW}⚠️  Redis will continue running${NC}"
fi

# Clean up any stale PID files
echo -e "${BLUE}Cleaning up PID files...${NC}"
if [ -d "$PID_DIR" ]; then
    # Check each PID file
    for pid_file in "$PID_DIR"/*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if ! ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${YELLOW}Removing stale PID file: $(basename "$pid_file")${NC}"
                rm -f "$pid_file"
            fi
        fi
    done
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   All Services Stopped Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Show any remaining Python processes (for debugging)
remaining_processes=$(ps aux | grep -E "python|celery|uvicorn" | grep -v grep | wc -l)
if [ "$remaining_processes" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Note: There are still $remaining_processes Python-related processes running:${NC}"
    ps aux | grep -E "python|celery|uvicorn" | grep -v grep
    echo ""
    echo "If these are Fintellic processes, you may need to kill them manually."
fi

echo "📁 Log files are preserved in: $PROJECT_ROOT/logs/"
echo ""
echo "🚀 To start all services again, run: ./scripts/start_fintellic.sh"