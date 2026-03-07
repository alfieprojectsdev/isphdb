# System Architecture: ISP Health Dashboard

## Overview
The ISP Health Dashboard is a local-first, lightweight network monitoring stack designed to continuously probe and visualize the health of your internet connection. It determines whether connectivity issues stem from your local home network (LAN), the connection to your ISP's node, or the broader internet backbone.

The system is broken into two decoupled components: a Python-based background daemon (the prober) and an Astro/NodeJS-based Server-Side Rendered (SSR) frontend.

---

## 1. The Backend (Python Prober)
**File location:** `backend/prober.py`

### Mechanism
The prober is an infinite loop script that wakes up every 30 seconds (`INTERVAL_SECONDS`) to perform ICMP pings against three crucial network layers:
1. **Local Router (`Auto-detected`)**: Indicates Wi-Fi/LAN health.
2. **ISP Gateway (`Auto-detected`)**: Indicates the physical line connecting your home to the neighborhood node.
3. **External DNS (`1.1.1.1`)**: Indicates broader internet routing health beyond your ISP.

### Dynamic Network Auto-Detection
The prober automatically adapts to whatever network the host machine is currently connected to (e.g., smoothly transitioning between a home Wi-Fi and an office LAN).
- **Local Router:** Discovered by executing `netstat -rn` (macOS) or `ip route` (Linux) and parsing the `default` routing table entry.
- **ISP Gateway:** Discovered by executing a 5-hop numeric traceroute out to Cloudflare (`1.1.1.1`) and parsing for the **first IP address that does not begin with `192.168.`**. This logic mathematically guarantees the detection of the true ISP handoff node, bypassing any local "Double NAT" configurations (such as a mesh router plugged into an ISP modem).

### Cross-Platform Architecture
To avoid the need for `root` or `sudo` privileges (which third-party libraries like `ping3` require for raw socket access), the application utilizes the host operating system's native `ping` utility via the Python `subprocess` module.

It dynamically inspects `sys.platform` to format commands appropriately:
- **macOS (`darwin`)**: Executes `ping -c 1 -t 2 <ip>`
- **Linux**: Executes `ping -c 1 -W 2 <ip>`

### Telemetry Storage
All results are appended to a local SQLite database (`backend/network_metrics.db`). The schema consists of a single `network_metrics` table with an indexed `timestamp` column for high-speed time-series retrieval. Total disconnections are stored with a latency of `-1.0` ms.

### Anomaly Detection & Alerting
The prober retains a rolling history of the last 10 minutes (20 data points) for the ISP Gateway. 
- If the current latency spikes to double the moving average **and** exceeds 50ms, or if the connection drops (`-1.0`), it bypasses standard logging to immediately trigger an OS-level desktop notification.
- **macOS:** Triggers via AppleScript (`osascript`)
- **Linux:** Triggers via `notify-send`

---

## 2. The Frontend (Astro Dashboard)
**Directory location:** `frontend/`

### Mechanism
The dashboard is built using [Astro](https://astro.build/) configured with the Node adapter for standalone Server-Side Rendering (SSR). This means it physically reads the SQLite database on the host machine every time a user requests the webpage, rather than generating static HTML files at build time.

### Data Hydration
In `src/pages/index.astro`, the server logic uses `better-sqlite3` to query the last 3 hours of telemetry data.
1. Outage mapping: Failed pings (`-1.0`) are intercepted and artificially boosted to `500` before being passed to the chart, turning invisible dropped packets into glaring red visual spikes on the UI.
2. The UI calculates dynamic "Don't Make Me Think" status cards based on the trailing 10 minutes of average performance, assigning a localized status (Green/Yellow/Red) without requiring the user to interpret the scatter plot.

### Visualization 
The raw data arrays are injected into an [Apache ECharts](https://echarts.apache.org/) instance rendered on an HTML5 `<canvas>`. The chart is configured with dynamic smoothing (`0.3`) and translucent `areaStyle` gradients for maximum readability.

### Home Network Accessibility (PWA)
The dashboard is structurally a Progressive Web App (PWA) equipped with a `manifest.json`.
Because the Astro Vite server is explicitly bound to all local network interfaces (`0.0.0.0`), any device (iPhone, Android, laptop) on the same Wi-Fi network can navigate to the host's LAN IP (`http://<HOST_IP>:4321`) and install the dashboard directly to their home screen as a native-feeling application.

---

## 3. Daemonization (System Services)
To survive reboots and run transparently, the stack utilizes native OS service managers.

### macOS (`launchd`)
Provided in `backend/com.user.isphealth.plist`. This XML file instructs the Apple `launchd` service to execute the prober via `uv run` on system load, persisting the process and dumping standard output/errors into `/tmp/` logs.

### Linux (`systemd`)
Provided in `backend/isp-health.service`. This INI-style configuration file serves a similar role for Linux distributions, allowing administrators to use `systemctl enable --now isp-health.service` to bind the prober to the network target lifecycle.
