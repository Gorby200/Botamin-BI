#!/usr/bin/env bash
# Botamin BI — Full build script
# Usage: ./build.sh --sheet "<Google Sheets URL>"
set -euo pipefail

SHEET="${1:-}"
if [ -z "$SHEET" ]; then
  echo "Usage: ./build.sh --sheet \"<Google Sheets URL>\""
  echo "   or: ./build.sh --file <path-to-csv>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "══════════════════════════════════════════════════"
echo "  Botamin BI — Full Build"
echo "══════════════════════════════════════════════════"

# 1. Run Python pipeline
echo ""
echo "[1/2] Running Python pipeline..."
source .venv/Scripts/activate
PYTHONUTF8=1 python -W ignore -m pipeline "$@"
echo "✅ Pipeline complete"

# 2. Build React frontend
echo ""
echo "[2/2] Building React frontend..."
cd frontend
npm ci --legacy-peer-deps
npm run build
cd ..
echo "✅ Frontend built"

echo ""
echo "══════════════════════════════════════════════════"
echo "  ✅ Build complete!"
echo "  Open frontend/dist/index.html in your browser"
echo "══════════════════════════════════════════════════"
