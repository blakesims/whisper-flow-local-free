#!/bin/bash

# Get the directory of the current script
script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate the Python virtual environment relative to the script directory
source "$script_dir/fabric-app-venv/bin/activate"

# Run the Python script with the desired arguments in the background
python "$script_dir/transcribe_pattern.py" --automated --model base --language english > "$script_dir/transcription.log" 2>&1 &

# Deactivate the virtual environment
deactivate
