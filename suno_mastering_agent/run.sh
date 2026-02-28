#!/bin/bash
# Suno Mastering Agent launcher

# Change to script directory so relative paths work
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium
else
    source venv/bin/activate
fi

# Run the agent
python main.py "$@"
