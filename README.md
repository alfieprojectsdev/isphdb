# ISP Health Dashboard

A local-first, lightweight time-series data collection and visualization system to monitor network health. It programmatically differentiates between Local Area Network (LAN) bottlenecks, ISP gateway failures, and wider internet backbone outages through continuous background ICMP polling.

📖 **[Read the Full System Architecture Explainer](ARCHITECTURE.md)**

## Features
- **Cross-Platform Backend:** Runs silently via native `subprocess` pings on macOS (`launchd`) and Linux (`systemd`).
- **Dynamic Network Auto-Detection:** Automatically discovers your active Local Router and ISP Gateway using intelligent `netstat` and `traceroute` parsing—no hardcoding required. Move seamlessly between home, office, and coffee shop networks. 
- **ICMP-Bypass (TCP Fallback):** Intelligently detects networks that aggressively block `ping` commands and dynamically fails over to raw TCP Socket connections (Port 53/80) to accurately measure gateway latency without triggering false offline alerts.
- **"Don't Make Me Think" Dashboard:** Dynamic green/yellow/red status banners that interpret latency without requiring you to read the chart.
- **Home Network Deployment:** Accessible to any browser on the LAN. 
- **PWA Ready:** Install the dashboard directly to any iOS/Android home screen.
- **Native OS Alerts:** Fires `osascript` (macOS) or `notify-send` (Linux) desktop alerts during critical congestion or outages.

## Project Structure

This project is separated into a `backend` daemon and a `frontend` dashboard.

* `backend/` - A Python script utilizing `sqlite3` and `subprocess.run` to execute and record pings every 30 seconds. Managed by `uv`.
* `frontend/` - An SSR Astro web PWA visualizing the SQLite data using Apache ECharts.

## Setup & Running

### 1. The Prober (Backend)

The backend daemon inherently monitors three distinct targets to isolate bottlenecks:
1. **Local Router (`Auto-detected`)**: The first hop (your Wi-Fi or LAN gateway).
2. **ISP Gateway (`Auto-detected`)**: The first public IP (bypassing local Double NAT).
3. **External DNS (`1.1.1.1`)**: Cloudflare's edge servers.

**Interactive Run:**
```bash
cd backend
uv run prober.py
```

### Quick Start (macOS & Linux)
We provide a universal helper script that automatically detects your OS, unzombies processes, restarts the Python background service, statically spawns the Astro UI server using `nohup`, and outputs your live Dashboard URLs to connect.

```bash
./reload-daemon.sh
```
*(If you travel between networks, simply re-run this script to automatically detect and bind to the new routers).*

You can still manage the background services manually if you prefer:

**1. The Prober (Backend)**
* macOS: `launchctl load -w backend/com.user.isphealth.plist`
* Linux: `sudo systemctl enable --now isp-health.service`
* Interactive: `cd backend && uv run prober.py`

**2. The Dashboard (Frontend)**
* Interactive: `cd frontend && npm install && npm run dev -- --host`

## Database

Data is logged locally to `backend/network_metrics.db`.
The `network_metrics` table has the following schema:
* `id` (INTEGER PRIMARY KEY)
* `timestamp` (DATETIME)
* `target_node` (TEXT)
* `latency_ms` (REAL)

## Future Improvements

* Desktop OS notifications are currently implemented via AppleScript (`osascript`) for macOS when the ISP latency exceeds baseline parameters by >200%.
