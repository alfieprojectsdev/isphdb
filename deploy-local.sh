#!/bin/bash
# ISP Health Dashboard - Local Deploy
# Wrapper around reload-daemon.sh that also opens the dashboard in a browser.
# reload-daemon.sh builds the frontend and (re)starts the services; this script
# adds the browser-open step. Idempotent: safe to re-run.

set -e

# Run from the repository root regardless of where the script is invoked
cd "$(dirname "$0")"

echo "=== ISP Health Local Deploy ==="

# 1. Build + install + (re)start services (build + OS detection live in reload-daemon.sh)
echo "[1/2] Building and deploying services..."
bash reload-daemon.sh

# 2. Open the dashboard in the default browser
URL="http://localhost:4321"
echo "[2/2] Opening ${URL} ..."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 &
else
  echo "No browser opener found (xdg-open/open). Visit ${URL} manually."
fi

echo "✅ Deploy complete."
