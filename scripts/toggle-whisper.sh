#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Toggle Whisper Daemon
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 🎙️
# @raycast.packageName Whisper

# Documentation:
# @raycast.description Start or stop the Whisper transcription daemon
# @raycast.author blake

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/whisper-daemon.pid"

if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
    # Daemon is running - stop it
    "$SCRIPT_DIR/whisper-daemon.sh" stop > /dev/null 2>&1
    echo "Whisper daemon stopped"
else
    # Daemon is not running - start it
    "$SCRIPT_DIR/whisper-daemon.sh" start > /dev/null 2>&1 &
    sleep 2
    if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
        echo "Whisper daemon started"
    else
        echo "Failed to start daemon"
    fi
fi
