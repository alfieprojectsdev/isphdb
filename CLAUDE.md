# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python Prober)
```bash
cd backend
uv run prober.py          # Run interactively
tail -f backend/prober.log # Check systemd daemon logs (Linux)
```

### Frontend (Astro Dashboard)
```bash
cd frontend
npm install
npm run dev               # Dev server at http://localhost:4321
npm run build             # Production build
npm run preview           # Preview production build
```

### Service Management

**macOS (launchd)** — `backend/com.user.isphealth.plist`:
```bash
launchctl load -w backend/com.user.isphealth.plist
launchctl unload -w backend/com.user.isphealth.plist
```

**Linux (systemd user services, no root required)** — `backend/isp-health.service` and `frontend/isp-health-frontend.service`:
```bash
# Install
cp backend/isp-health.service ~/.config/systemd/user/
cp frontend/isp-health-frontend.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now isp-health.service
systemctl --user enable --now isp-health-frontend.service
loginctl enable-linger $USER   # persist after logout

# Check status / logs
systemctl --user status isp-health.service
systemctl --user status isp-health-frontend.service
tail -f backend/prober.log
```

The frontend production build must exist before starting the frontend service:
```bash
cd frontend && npm run build
```
The standalone node server binds to `HOST=0.0.0.0 PORT=4321`, making the dashboard reachable at `http://<LAN_IP>:4321` from any device on the home network.

## Architecture

Two fully decoupled components share a single SQLite database file:

**`backend/prober.py`** — An infinite-loop Python daemon (managed by `uv`, Python 3.12) that pings three network layers every 30 seconds using the OS native `ping` binary (no root required). It writes results to `backend/network_metrics.db`. It also runs anomaly detection on ISP gateway latency (rolling 20-sample window) and fires OS desktop alerts via `osascript` (macOS) or `notify-send` (Linux).

**`frontend/src/pages/index.astro`** — A single-page Astro SSR app that reads the SQLite DB directly at request time via `better-sqlite3`, transforms the last 3 hours of data, and renders an Apache ECharts scatter/line chart. The page auto-reloads every 30 seconds via `setTimeout`. The Vite server binds to `0.0.0.0` so it is accessible to any device on the LAN.

### Key Design Decisions
- The frontend reads the DB at SSR time on each page request — there is no API layer or WebSocket.
- Failed pings are stored as `-1.0` ms and mapped to `500` in the frontend for visual display as red spikes.
- Status classification (Healthy/Degraded/High Latency) is computed from the last 20 data points (~10 minutes) on the frontend.
- ECharts is loaded from CDN (`echarts@5.5.0`) in the HTML head, not bundled.
- The DB path can be overridden with the `DB_PATH` environment variable (defaults to `../backend/network_metrics.db` relative to `process.cwd()`).

### Network Targets
| Key | IP | Meaning |
|-----|----|---------|
| `local` | `192.168.1.1` | LAN/Wi-Fi health |
| `isp_gateway` | `10.56.0.1` | Physical ISP line (hop 3, bypasses Double NAT) |
| `external_dns` | `1.1.1.1` | Broader internet routing |

### DB Schema
Single table `network_metrics`: `id`, `timestamp` (DATETIME, indexed), `target_node` (TEXT), `latency_ms` (REAL).
