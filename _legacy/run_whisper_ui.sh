#!/bin/bash

# Get the directory of the current script (_legacy/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
VENV_NAME=".venv"

# Change to _legacy directory so Python finds the local app/ package (with symlinks)
builtin cd "$SCRIPT_DIR"

# Activate the Python virtual environment
if [ -f "$PROJECT_ROOT/$VENV_NAME/bin/activate" ]; then
  source "$PROJECT_ROOT/$VENV_NAME/bin/activate"
else
  echo "Virtual environment not found at $PROJECT_ROOT/$VENV_NAME"
  exit 1
fi

echo "Launching Legacy Whisper Transcription UI..."
python main.py

# Deactivate when done
if [ -n "$VIRTUAL_ENV" ]; then
  deactivate
fi
