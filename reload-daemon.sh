#!/bin/bash
# ISP Health Dashboard - Daemon Service Manager
# Automatically unloads and reloads the background prober daemon across macOS and Linux.

set -e

# Change directory to the repository root so relative paths work
cd "$(dirname "$0")"

echo "=== ISP Health Daemon Manager ==="

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[OS Detected] Linux (systemd)"
    echo "Stopping existing systemd service..."
    sudo systemctl stop isp-health.service || true
    
    echo "Copying latest service template to systemd..."
    sudo cp backend/isp-health.service /etc/systemd/system/
    sudo systemctl daemon-reload
    
    echo "Starting systemd service..."
    sudo systemctl enable --now isp-health.service
    echo "✅ Linux Daemon is now running!"

elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "[OS Detected] macOS (launchd)"
    
    echo "Unloading existing launchd plist (if any)..."
    launchctl unload -w backend/com.user.isphealth.plist 2>/dev/null || true
    
    # Just in case there are lingering Python subprocesses
    echo "Killing any orphaned prober processes..."
    pkill -f "prober.py" || true
    
    echo "Reloading launchd plist..."
    launchctl load -w backend/com.user.isphealth.plist
    echo "✅ macOS Daemon is now running!"

else
    echo "Unsupported OS: $OSTYPE. Please run the backend interactively via 'uv run backend/prober.py'."
    exit 1
fi

echo ""
echo "Note: The Python prober inherently auto-detects your active Local Router and ISP Gateway on startup."
echo "If you swap between home and office networks, simply re-run this script to bind the daemon to the new network."
echo ""

# Output the Dashboard URLs
echo "=== Dashboard Access ==="
echo "Local Access: http://localhost:4321"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Try getting primary en0 interface IP first, then en1 if fallback needed
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
else
    # Linux hostname -I returns all IPs, grab the first one
    LOCAL_IP=$(hostname -I | awk '{print $1}')
fi

if [ ! -z "$LOCAL_IP" ]; then
    echo "Network/Mobile Access: http://$LOCAL_IP:4321"
fi
