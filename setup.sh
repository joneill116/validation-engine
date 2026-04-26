#!/bin/bash
# Setup script for validation-engine (Linux/macOS)
# Run: chmod +x setup.sh && ./setup.sh

set -e  # Exit on error

echo "🔧 Setting up validation-engine..."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found!"
    echo "Install Python 3.11+ first:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install pytest pyyaml

echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the environment in your shell:"
echo "  source .venv/bin/activate"
echo ""
echo "Quick start:"
echo "  python3 run_validation.py config_equity.yaml sample_data.csv"
echo "  python3 run_tests.py"
echo ""
echo "Or make scripts executable:"
echo "  chmod +x run_validation.py run_tests.py"
echo "  ./run_validation.py config_equity.yaml sample_data.csv"
