#!/bin/bash

# Get the directory of the current script (i.e., your project root)
APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_NAME=".venv" # Adjust if your virtual environment has a different name (e.g., venv, fabric-app-venv)

echo "Changing to app directory: $APP_DIR"
cd "$APP_DIR"

# Activate the Python virtual environment
# Check if venv exists and activate
if [ -f "$VENV_NAME/bin/activate" ]; then # Common check for venv
  echo "Activating virtual environment: $VENV_NAME"
  source "$VENV_NAME/bin/activate"
else
  # Attempt path relative to script_dir if APP_DIR is different
  if [ -f "$APP_DIR/$VENV_NAME/bin/activate" ]; then
    echo "Activating virtual environment: $APP_DIR/$VENV_NAME"
    source "$APP_DIR/$VENV_NAME/bin/activate"
  else
    echo "Virtual environment $VENV_NAME not found in $APP_DIR. Running with system Python."
  fi
fi

echo "Launching Whisper Transcription UI..."
# We use 'python -m app.main' as per our previous discussions to ensure modules are found
python -m app.main

# Deactivate the virtual environment when the app closes
# This part will only execute after the Python GUI application has terminated.
if [ -n "$VIRTUAL_ENV" ]; then
  echo "Deactivating virtual environment..."
  deactivate
fi

echo "Whisper UI script finished."
