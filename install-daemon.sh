#!/bin/bash
#
# Install Whisper Daemon for Auto-Start on Login
#
# This script:
# 1. Installs the launchd plist to ~/Library/LaunchAgents/
# 2. Loads the daemon so it starts immediately
# 3. Sets up auto-start on login
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.user.whisper-daemon.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Whisper Daemon Installer${NC}"
echo "========================="
echo ""

# Check if plist source exists
if [ ! -f "$PLIST_SRC" ]; then
    echo -e "${RED}Error: Plist file not found: $PLIST_SRC${NC}"
    exit 1
fi

# Check virtual environment
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not found${NC}"
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    source "$SCRIPT_DIR/.venv/bin/activate"
    echo "Installing dependencies..."
    pip install -r "$SCRIPT_DIR/requirements.txt"
    echo ""
fi

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing daemon if running
if launchctl list | grep -q "com.user.whisper-daemon"; then
    echo -e "${YELLOW}Stopping existing daemon...${NC}"
    launchctl unload "$PLIST_DEST" 2>/dev/null
fi

# Update the plist with the correct paths
echo -e "${GREEN}Updating plist with your paths...${NC}"

# Create a temporary plist with updated paths
PYTHON_PATH="$SCRIPT_DIR/.venv/bin/python"
cat > "$PLIST_DEST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.whisper-daemon</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>-m</string>
        <string>app.daemon.whisper_daemon</string>
        <string>start</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$SCRIPT_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>$SCRIPT_DIR</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/whisper-daemon.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/whisper-daemon.log</string>

    <key>ProcessType</key>
    <string>Interactive</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

echo -e "${GREEN}Plist installed to: $PLIST_DEST${NC}"

# Load the daemon
echo -e "${GREEN}Loading daemon...${NC}"
launchctl load "$PLIST_DEST"

# Wait for daemon to start
sleep 3

# Check if running
if launchctl list | grep -q "com.user.whisper-daemon"; then
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}Whisper Daemon installed and running!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "The daemon will:"
    echo "  - Start automatically when you log in"
    echo "  - Keep the Whisper model loaded in memory"
    echo "  - Listen for Ctrl+F global hotkey"
    echo ""
    echo "Usage:"
    echo "  - Press Ctrl+F to start recording"
    echo "  - Press Ctrl+F again to stop and auto-paste"
    echo ""
    echo "Management commands:"
    echo "  ./whisper-daemon.sh status  - Check status"
    echo "  ./whisper-daemon.sh stop    - Stop daemon"
    echo "  ./whisper-daemon.sh start   - Start daemon"
    echo "  ./whisper-daemon.sh logs    - View logs"
    echo ""
    echo -e "${YELLOW}Note: Grant Accessibility permissions when prompted${NC}"
    echo "System Preferences > Privacy & Security > Accessibility"
else
    echo -e "${RED}Daemon may have failed to start${NC}"
    echo "Check logs: /tmp/whisper-daemon.log"
    echo ""
    tail -20 /tmp/whisper-daemon.log 2>/dev/null
fi

echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  rm ~/Library/LaunchAgents/$PLIST_NAME"
