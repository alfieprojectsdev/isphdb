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
- Rows older than 30 days are pruned periodically by the prober; the DB runs in WAL mode for concurrent reader/writer access.
- ECharts is loaded from CDN (`echarts@5.5.0`) in the HTML head, not bundled.
- The DB path can be overridden with the `DB_PATH` environment variable (defaults to `../backend/network_metrics.db` relative to `process.cwd()`).

### Network Targets
Targets are auto-detected at startup; the values below are examples only.

| Key | Example IP | Meaning |
|-----|----|------|
| `local` | `192.168.1.1` | LAN/Wi-Fi health (default gateway) |
| `isp_gateway` | auto-detected | Physical ISP line (first non-192.168.* traceroute hop) |
| `external_dns` | `1.1.1.1` | Broader internet routing |

### DB Schema
Table `network_metrics`: `id`, `timestamp` (DATETIME, indexed), `target_node` (TEXT), `latency_ms` (REAL).

Table `traceroute_hops`: `id`, `timestamp` (DATETIME, indexed), `hop_index` (INTEGER), `hop_ip` (TEXT), `latency_ms` (REAL). The prober captures the full hop path to `1.1.1.1` every `TRACEROUTE_CYCLES` (10, ~5 min), storing one row per geolocatable (public) hop; rows sharing a `timestamp` form one capture. Only mappable hops are persisted — LAN/CGNAT hops are excluded via `is_mappable_hop`. The dashboard reads the most recent capture for the geo map. Pruned on the same 30-day retention as `network_metrics`.

### Traceroute-Hop Geo Overlay
The dashboard renders a "Route Geography" panel below the latency chart: the latest `traceroute_hops` capture joined against a curated static IP→geo table (`frontend/src/lib/hop-geo.json`, keyed by IP/CIDR) and drawn on a low-res Philippines map (`frontend/public/philippines.geo.json`) via `echarts.registerMap`, colored by latency. Pure lookup/color helpers live in `frontend/src/lib/geo.mjs`. `backend/geo_seed.py` is a dev-only script to refresh the geo table from a public API — the daemon never calls it. No runtime geo API calls, no new dependencies.
