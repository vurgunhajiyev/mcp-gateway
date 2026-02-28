#!/usr/bin/env bash
# Development environment setup script
set -euo pipefail

echo "🔧 Setting up MCP Gateway development environment..."

# Check Python version
python3 --version | grep -qE "3\.(11|12|13)" || {
    echo "❌ Python 3.11+ is required"
    exit 1
}

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -e ".[dev]"

# Copy env file
if [ ! -f ".env" ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
fi

# Create log directory
mkdir -p logs

echo ""
echo "✅ Setup complete!"
echo ""
echo "Start the gateway:"
echo "  source .venv/bin/activate"
echo "  python -m src.main"
echo ""
echo "Start with Docker:"
echo "  docker compose up -d"
echo ""
echo "Run tests:"
echo "  pytest -v"
