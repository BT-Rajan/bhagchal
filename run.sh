#!/bin/bash
# Baghchal — quick start script
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "Starting Baghchal server..."
echo "Open http://127.0.0.1:5000 in your browser"
echo "Demo login: admin / admin   or   guest / guest"
echo ""

python3 app.py
