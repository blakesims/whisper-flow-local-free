#!/bin/bash

# Build script for Whisper Transcription UI macOS app

echo "🔨 Building Whisper Transcription UI..."

# Get the directory of the current script
APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$APP_DIR"

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist

# Ensure virtual environment is activated
if [ -f ".venv/bin/activate" ]; then
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found. Please create it first with:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Build the app
echo "📦 Building macOS app bundle..."
python setup.py py2app

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
    echo "📂 App location: $APP_DIR/dist/Whisper Transcription UI.app"
    
    # Optional: Open the dist folder
    open dist/
else
    echo "❌ Build failed!"
    exit 1
fi