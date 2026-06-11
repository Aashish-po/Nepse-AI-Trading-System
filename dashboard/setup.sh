#!/bin/bash
# Quick-start setup for NEPSE AI Trading Dashboard
# Compatible with Windows (Git Bash) and macOS/Linux

set -e

echo " NEPSE AI Trading Dashboard - Quick Start Setup"
echo "=================================================="
echo ""

# Check Python version
echo "✓ Checking Python version..."
python --version || {
    echo " Python not found. Install Python 3.10+ from https://www.python.org/"
    exit 1
}

# Create virtual environment
echo ""
echo "✓ Creating virtual environment..."
if [ ! -d "venv" ]; then
    python -m venv venv
    echo "  Created: venv/"
else
    echo "  Already exists: venv/"
fi

# Activate virtual environment
echo ""
echo "✓ Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Upgrade pip
echo ""
echo "✓ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "✓ Installing dependencies..."
pip install -r requirements-dasboard.txt

# Create Streamlit directory
echo ""
echo "✓ Setting up Streamlit configuration..."
mkdir -p .streamlit

# Create secrets.toml if it doesn't exist
if [ ! -f ".streamlit/secrets.toml" ]; then
    cat > .streamlit/secrets.toml <<EOF
# NEPSE AI Trading System API Configuration
API_BASE = "http://localhost:8000"
EOF
    echo "  Created: .streamlit/secrets.toml"
    echo "  Edit this file to configure your backend URL"
else
    echo "  Already exists: .streamlit/secrets.toml"
fi

# Copy config.toml
if [ ! -f ".streamlit/config.toml" ]; then
    cp .streamlit_config.toml .streamlit/config.toml 2>/dev/null || {
        echo "    Run: cp .streamlit_config.toml .streamlit/config.toml"
    }
fi

echo ""
echo "=================================================="
echo " Setup Complete!"
echo ""
echo " Next Steps:"
echo "1. Start the backend API:"
echo "   cd ../backend"
echo "   python -m uvicorn app.main:app --reload"
echo ""
echo "2. In another terminal, start the dashboard:"
echo "   streamlit run app.py"
echo ""
echo "3. Open your browser to http://localhost:8501"
echo ""
echo " Documentation: See dashboard/README.md"
echo "=================================================="
echo ""     