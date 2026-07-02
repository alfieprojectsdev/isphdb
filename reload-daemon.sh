#!/bin/bash
# ISP Health Dashboard - Daemon Service Manager
# Automatically unloads and reloads the background prober daemon across macOS and Linux.

set -e

# Change directory to the repository root so relative paths work
cd "$(dirname "$0")"

echo "=== ISP Health Daemon Manager ==="

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[OS Detected] Linux (systemd --user)"
    REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
    UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"

    echo "Building frontend production bundle..."
    ( cd frontend && npm install --no-audit --no-fund && npm run build )
    if [ ! -f frontend/dist/server/entry.mjs ]; then
        echo "❌ Frontend build failed (frontend/dist/server/entry.mjs missing). Aborting before touching services." >&2
        exit 1
    fi

    echo "Stopping existing systemd user services..."
    systemctl --user stop isp-health.service 2>/dev/null || true
    systemctl --user stop isp-health-frontend.service 2>/dev/null || true

    echo "Installing unit files to user systemd directory..."
    mkdir -p ~/.config/systemd/user
    cp backend/isp-health.service ~/.config/systemd/user/
    cp frontend/isp-health-frontend.service ~/.config/systemd/user/

    sed -i "s|/home/finch/repos/isphdb|$REPO_ROOT|g" ~/.config/systemd/user/isp-health.service ~/.config/systemd/user/isp-health-frontend.service
    if grep -q '/home/finch/.local/bin/uv' ~/.config/systemd/user/isp-health.service; then
        sed -i "s|/home/finch/.local/bin/uv|$UV_BIN|g" ~/.config/systemd/user/isp-health.service
    fi

    systemctl --user daemon-reload

    echo "Starting systemd user services..."
    systemctl --user enable --now isp-health.service
    systemctl --user enable --now isp-health-frontend.service
    echo "✅ Linux services are now running!"
    echo "Note: Run 'loginctl enable-linger $USER' to persist services past logout."

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

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo "=== Starting Astro Dashboard (Frontend) ==="
    echo "Stopping any existing Astro dev servers..."
    pkill -f "astro dev" || true

    echo "Starting Astro dev server in the background..."
    cd frontend
    nohup npm run dev -- --host > /dev/null 2>&1 &
    cd ..
    echo "✅ Frontend server is now running!"
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
