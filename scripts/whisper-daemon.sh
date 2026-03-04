#!/bin/bash
#
# Whisper Daemon Control Script
# Usage: ./whisper-daemon.sh [start|stop|status|restart]
#

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from scripts/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
DAEMON_MODULE="app.daemon.whisper_daemon"
PID_FILE="/tmp/whisper-daemon.pid"

# cc-triage daemon (delegation routing)
TRIAGE_DIR="$HOME/projects/cc-triage"
TRIAGE_VENV="$TRIAGE_DIR/.venv"
TRIAGE_PID_FILE="/tmp/cc-triage-daemon.pid"
TRIAGE_LOG="/tmp/cc-triage-daemon.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment exists
check_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        echo -e "${RED}Error: Virtual environment not found at $VENV_PATH${NC}"
        echo "Run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

# Activate virtual environment
activate_venv() {
    source "$VENV_PATH/bin/activate"
}

# Get daemon status
get_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "running"
            return 0
        fi
    fi
    echo "stopped"
    return 1
}

# Start the daemon
start_daemon() {
    if [ "$(get_status)" = "running" ]; then
        PID=$(cat "$PID_FILE")
        echo -e "${YELLOW}Whisper daemon is already running (PID: $PID)${NC}"
        return 1
    fi

    echo -e "${GREEN}Starting Whisper daemon...${NC}"
    check_venv
    activate_venv

    cd "$PROJECT_ROOT"

    # Run daemon in background, redirect output to log file
    LOG_FILE="/tmp/whisper-daemon.log"
    nohup python -u -m "$DAEMON_MODULE" start > "$LOG_FILE" 2>&1 &

    # Wait a moment for daemon to start
    sleep 2

    if [ "$(get_status)" = "running" ]; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}Whisper daemon started successfully (PID: $PID)${NC}"
        echo "Log file: $LOG_FILE"
        echo ""
        echo "Press Ctrl+F to start/stop recording"

        # Start cc-triage alongside whisper
        start_triage
    else
        echo -e "${RED}Failed to start daemon. Check log: $LOG_FILE${NC}"
        tail -20 "$LOG_FILE"
        return 1
    fi
}

# Stop the daemon
stop_daemon() {
    if [ "$(get_status)" = "stopped" ]; then
        echo -e "${YELLOW}Whisper daemon is not running${NC}"
        return 0
    fi

    PID=$(cat "$PID_FILE")
    echo -e "${YELLOW}Stopping Whisper daemon (PID: $PID)...${NC}"

    # Send SIGTERM for graceful shutdown
    kill -TERM "$PID" 2>/dev/null

    # Wait for process to stop (up to 5 seconds)
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}Whisper daemon stopped${NC}"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 0.5
    done

    # Force kill if still running
    echo -e "${YELLOW}Daemon didn't stop gracefully, forcing...${NC}"
    kill -KILL "$PID" 2>/dev/null
    rm -f "$PID_FILE"
    echo -e "${GREEN}Whisper daemon stopped (forced)${NC}"

    # Stop cc-triage alongside whisper
    stop_triage
}

# Show daemon status
show_status() {
    if [ "$(get_status)" = "running" ]; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}Whisper daemon is RUNNING${NC}"
        echo "  PID: $PID"
        echo "  Log: /tmp/whisper-daemon.log"

        # Show memory usage
        MEM=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.1f MB", $1/1024}')
        echo "  Memory: $MEM"

        # Show uptime
        STARTED=$(ps -o lstart= -p "$PID" 2>/dev/null | xargs)
        echo "  Started: $STARTED"

        # Show model from log
        MODEL=$(grep "Model.*loaded successfully" /tmp/whisper-daemon.log 2>/dev/null | tail -1 | sed 's/.*Model \([^ ]*\).*/\1/')
        if [ -n "$MODEL" ]; then
            echo "  Model: $MODEL"
        fi

        echo ""
        echo -e "${YELLOW}Hotkey: Ctrl+F${NC} to toggle recording"

        # cc-triage status
        if [ -f "$TRIAGE_PID_FILE" ] && ps -p "$(cat "$TRIAGE_PID_FILE")" > /dev/null 2>&1; then
            TPID=$(cat "$TRIAGE_PID_FILE")
            TMEM=$(ps -o rss= -p "$TPID" 2>/dev/null | awk '{printf "%.1f MB", $1/1024}')
            echo ""
            echo -e "${GREEN}cc-triage daemon is RUNNING${NC}"
            echo "  PID: $TPID | Memory: $TMEM"
        else
            echo ""
            echo -e "${RED}cc-triage daemon is NOT running${NC}"
        fi
    else
        echo -e "${RED}Whisper daemon is NOT running${NC}"
        echo ""
        echo "Start with: $0 start"
    fi
}

# Show recent logs
show_logs() {
    LOG_FILE="/tmp/whisper-daemon.log"
    if [ -f "$LOG_FILE" ]; then
        echo -e "${GREEN}Recent daemon logs:${NC}"
        echo "---"
        tail -30 "$LOG_FILE"
    else
        echo -e "${YELLOW}No log file found${NC}"
    fi
}

# Show available models
show_models() {
    echo -e "${BLUE}Available Whisper Models:${NC}"
    echo ""
    echo "  tiny    - Fastest, lowest quality (~75MB)"
    echo "  base    - Fast, good quality (~140MB) [DEFAULT]"
    echo "  small   - Balanced (~500MB)"
    echo "  medium  - High quality (~1.5GB)"
    echo "  large-v2 - Best quality (~3GB)"
    echo ""
    echo "To change model, edit: ~/Library/Application Support/WhisperTranscribeUI/settings.json"
    echo "Set \"transcription_model_name\" to your preferred model, then restart daemon."
}

# Start cc-triage daemon
start_triage() {
    if [ -f "$TRIAGE_PID_FILE" ] && ps -p "$(cat "$TRIAGE_PID_FILE")" > /dev/null 2>&1; then
        return 0  # already running
    fi

    if [ ! -d "$TRIAGE_VENV" ]; then
        echo -e "${YELLOW}cc-triage venv not found, skipping${NC}"
        return 1
    fi

    (
        cd "$TRIAGE_DIR"
        unset ANTHROPIC_API_KEY
        nohup "$TRIAGE_VENV/bin/python" src/daemon.py > "$TRIAGE_LOG" 2>&1 &
        echo $! > "$TRIAGE_PID_FILE"
    )
    echo -e "${GREEN}cc-triage daemon started${NC}"
}

# Stop cc-triage daemon
stop_triage() {
    if [ -f "$TRIAGE_PID_FILE" ]; then
        PID=$(cat "$TRIAGE_PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -TERM "$PID" 2>/dev/null
            for i in {1..6}; do
                ps -p "$PID" > /dev/null 2>&1 || break
                sleep 0.5
            done
            kill -KILL "$PID" 2>/dev/null
        fi
        rm -f "$TRIAGE_PID_FILE"
    fi
}

# Main script logic
case "${1:-status}" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        stop_daemon
        sleep 1
        start_daemon
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    models)
        show_models
        ;;
    *)
        echo "Whisper Daemon Control"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|models}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the daemon in background"
        echo "  stop    - Stop the running daemon"
        echo "  restart - Restart the daemon"
        echo "  status  - Show daemon status and metrics"
        echo "  logs    - Show recent daemon logs"
        echo "  models  - Show available Whisper models"
        echo ""
        echo "Hotkey: Ctrl+F to toggle recording"
        ;;
esac
