#!/bin/bash

# Get the directory of the current script (_legacy/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Project root is the parent directory
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
VENV_NAME=".venv"

echo "Project root: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# Activate the Python virtual environment
if [ -f "$PROJECT_ROOT/$VENV_NAME/bin/activate" ]; then
  echo "Activating virtual environment: $VENV_NAME"
  source "$PROJECT_ROOT/$VENV_NAME/bin/activate"
else
  echo "Virtual environment $VENV_NAME not found. Running with system Python."
fi

# Add _legacy to PYTHONPATH so 'from app.ui' imports from _legacy/ui/
# This makes _legacy/ui appear as app/ui to Python
export PYTHONPATH="$SCRIPT_DIR:$PROJECT_ROOT:$PYTHONPATH"

echo "Launching Legacy Whisper Transcription UI..."
python "$SCRIPT_DIR/main.py"

# Deactivate the virtual environment when the app closes
# This part will only execute after the Python GUI application has terminated.
if [ -n "$VIRTUAL_ENV" ]; then
  echo "Deactivating virtual environment..."
  deactivate
fi

echo "Whisper UI script finished."
