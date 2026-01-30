#!/bin/bash
# Deploy KB Serve as a systemd service on Linux server (zen)
#
# Usage:
#   ./deploy/deploy-kb-serve.sh          # Install and start service
#   ./deploy/deploy-kb-serve.sh status   # Check service status
#   ./deploy/deploy-kb-serve.sh logs     # View recent logs
#   ./deploy/deploy-kb-serve.sh stop     # Stop service
#   ./deploy/deploy-kb-serve.sh restart  # Restart service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="kb-serve"
SERVICE_FILE="$SCRIPT_DIR/kb-serve.service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check if running on Linux
if [[ "$(uname)" != "Linux" ]]; then
    error "This script is for Linux (systemd) only. Use launchd on macOS."
fi

# Handle commands
case "${1:-install}" in
    install)
        info "Deploying KB Serve service..."

        # Check service file exists
        if [[ ! -f "$SERVICE_FILE" ]]; then
            error "Service file not found: $SERVICE_FILE"
        fi

        # Check venv exists
        if [[ ! -f "$REPO_DIR/.venv/bin/python" ]]; then
            error "Virtual environment not found. Run: cd $REPO_DIR && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        fi

        # Create ~/.kb directory if needed
        mkdir -p ~/.kb/inbox

        # Copy service file
        sudo cp "$SERVICE_FILE" /etc/systemd/system/
        info "Copied service file to /etc/systemd/system/"

        # Reload systemd
        sudo systemctl daemon-reload
        info "Reloaded systemd daemon"

        # Enable service (start on boot)
        sudo systemctl enable "$SERVICE_NAME"
        info "Enabled service for auto-start on boot"

        # Start service
        sudo systemctl start "$SERVICE_NAME"
        info "Started $SERVICE_NAME service"

        # Show status
        echo ""
        sudo systemctl status "$SERVICE_NAME" --no-pager

        echo ""
        info "KB Serve deployed successfully!"
        info "Access dashboard at: http://zen:8765"
        info "View logs with: $0 logs"
        ;;

    status)
        sudo systemctl status "$SERVICE_NAME" --no-pager
        ;;

    logs)
        journalctl -u "$SERVICE_NAME" -f --no-pager -n 50
        ;;

    stop)
        sudo systemctl stop "$SERVICE_NAME"
        info "Stopped $SERVICE_NAME"
        ;;

    restart)
        sudo systemctl restart "$SERVICE_NAME"
        info "Restarted $SERVICE_NAME"
        sudo systemctl status "$SERVICE_NAME" --no-pager
        ;;

    uninstall)
        warn "Uninstalling KB Serve service..."
        sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
        sudo systemctl daemon-reload
        info "Uninstalled $SERVICE_NAME service"
        ;;

    *)
        echo "Usage: $0 {install|status|logs|stop|restart|uninstall}"
        exit 1
        ;;
esac
