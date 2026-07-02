# Session Log: ISP Health Dashboard

## Accomplishments

During this session, we built and deployed a complete **ISP Health Dashboard** from scratch, transitioning from a basic specification to a fully functional, local-first web application.

Here is a summary of what was accomplished:

1. **Backend Daemon (Python)**
   * Built a robust polling script (`prober.py`) that utilizes native macOS `ping` commands to avoid requiring root/sudo privileges.
   * Monitored three critical network hops: Local Router (Wi-Fi/LAN), ISP Gateway (bypassing Double NAT), and Global Internet (Cloudflare DNS).
   * Implemented persistent time-series storage using a local SQLite database (`network_metrics.db`).
   * Added anomaly detection that uses rolling moving averages to identify latency spikes or complete outages, triggering native macOS desktop notifications (`osascript`).
   * Created a MacOS `launchd` plist (`com.user.isphealth.plist`) to daemonize the prober so it runs silently in the background on system startup.

2. **Frontend Dashboard (Astro + ECharts)**
   * Scaffolded a new Server-Side Rendered (SSR) Astro application running on the Node adapter.
   * Connected the frontend directly to the SQLite database using `better-sqlite3` robustly via absolute pathing.
   * Integrated **Apache ECharts** to turn raw telemetry into a dynamic, dark-themed time-series line chart.
   * Enhanced the graph aesthetics with `0.3` line smoothing, custom coloring, and glowing area gradient overlays.

3. **UI/UX & Mobile Capabilities (PWA)**
   * Implemented "Don't Make Me Think" UI principles by explicitly defining a color-coded legend.
   * Built an intelligent status banner that calculates the last 10 minutes of connectivity and provides a human-readable interpretation of the network state (e.g., "All Systems Nominal" vs "ISP Gateway Congestion").
   * Transformed the dashboard into a **Progressive Web App (PWA)** by injecting mobile meta tags, crafting a custom SVG icon, and adding a `manifest.json`.
   * Bound the Astro dev server to the local network (`0.0.0.0`), allowing any device in the house (like an iPhone) to "Install to Home Screen" and view the dashboard natively without deploying to the public internet or an app store.

4. **Version Control**
   * Initialized a local Git repository and pushed the entire finalized codebase to a remote GitHub repository (`alfieprojectsdev/isphdb`).

---

## Session 2

5. **Linux Cross-Platform Support**
   * Fixed `prober.py` to dynamically select the correct `ping` timeout flag at runtime: `-W` on Linux vs `-t` on macOS. The original hardcoded `-t` flag was silently setting TTL=2 on Linux, causing all pings to fail.
   * Fixed alert notifications to use `notify-send` on Linux instead of the macOS-only `osascript`.
   * Extracted alert logic into a `send_alert()` helper for clean platform branching.

6. **Linux Systemd Deployment (No Root Required)**
   * Created `backend/isp-health.service` and `frontend/isp-health-frontend.service` as systemd **user** units, installable without `sudo`.
   * Built the Astro frontend for production (`npm run build`) and configured the standalone Node server to bind to `HOST=0.0.0.0 PORT=4321`.
   * Enabled `loginctl enable-linger` so both services survive user logout and start automatically on boot.
   * Both services are live: the prober writing to SQLite, the dashboard accessible across the home network at `http://<LAN_IP>:4321`.

7. **Documentation**
   * Added `TECHDOCS.md` with build/run commands and a high-level architecture summary for future development sessions.
   * Updated `TECHDOCS.md` with full Linux service install, status, and log commands.

---

## Session 3

8. **Repository Hygiene**
   * Gitignored `network_metrics.db` (runtime artifact, recreated by prober on first run) and `*.log` files.
   * Untracked `network_metrics.db` from git history via `git rm --cached`.
   * Committed updated `frontend/package-lock.json`.

9. **Network Reconfiguration (Institutional Network)**
   * Moved deployment to an institutional network (`192.168.x.x`).
   * Ran `traceroute` to identify new hops: local router (hop 1), ISP gateway (hop 2, first public IP — no double NAT on this network).
   * Updated `LOCAL_ROUTER_IP` and `ISP_GATEWAY_IP` in `prober.py` accordingly.
   * Fixed stdout log buffering by adding `PYTHONUNBUFFERED=1` to `isp-health.service` — logs were silently buffered when Python stdout was redirected to a file.
   * Dashboard live at `http://<LAN_IP>:4321` on the institutional network.

---

## Session 4

10. **Housekeeping & Shutdown**
    * Confirmed services still running on the institutional network.
    * Stopped both `isp-health.service` and `isp-health-frontend.service` cleanly before logging off.

---

## Session 5

11. **Dynamic Network Auto-Detection**
    * Implemented intelligent cross-platform gateway detection in `prober.py`.
    * Discovers Local Router via `netstat -rn` (macOS) or `ip route` (Linux).
    * Discovers true ISP Gateway by parsing a 5-hop `traceroute` to `1.1.1.1` and filtering out Double NAT (`192.168.*`) local IP addresses.
    * Removed hardcoded `LOCAL_ROUTER_IP` and `ISP_GATEWAY_IP` dependencies.

12. **Universal Service Management**
    * Created `reload-daemon.sh` shell script to simplify daemon management.
    * Automatically detects OS (Darwin vs Linux) to execute `launchctl` or `systemctl` cleanly.
    * Enhanced script to automatically detect host IP (`ipconfig` / `hostname -I`) and echo dashboard URLs (`http://<IP>:4321`) to the user upon restart.
    * Refactored script to automatically track down orphaned Astro UI servers and spawn a new Server-Side Rendered (SSR) Dashboard detached via `nohup`, ensuring both backend and frontend layers run simultaneously from one command.

13. **ICMP-Bypass (TCP Fallback)**
    * Discovered that enterprise/public networks often firewall and aggressively drop native `ping` (ICMP Echo Request) packets.
    * Implemented an intelligent `tcp_ping()` fallback in `prober.py` that utilizes native python Sockets to connect to Port 53 (DNS) instead, successfully measuring router hop latencies without triggering the firewall.
    * Added intelligence to `index.astro` to override false-positive "Offline" UI alerts if the backend detects that the internal router is dropping pings but the broader internet (DNS) is still reachable.

---

## Session 6

14. **Git Sync & Repository Maintenance**
    * Resolved a diverged branch state between local `main` and `origin/main`.
    * Diagnosed a `skip-worktree` bit on `session_log.md` that was hiding a real file difference from `git status`, causing `git pull --rebase` to abort with a misleading "local changes" error.
    * Cleared the `skip-worktree` flag via `git update-index --no-skip-worktree` and completed a clean rebase, integrating 3 upstream commits (TCP fallback UI fix, README/session log updates) with the local CLAUDE.md restore commit.

---

## Session 7 — Planner Hardening, Deploy & Live-Monitoring Fixes

15. **Planner-Driven Correctness/Robustness Pass (`plan.json` → 4 milestones)**
    * M-001 `prober.py`: shell-safe alerts via `subprocess.run` argv (no `os.system`); WAL + `busy_timeout=5000`; anomaly moving-average/spike check now runs every warm cycle (not only on window pop); 30-day retention prune; SIGINT/SIGTERM graceful commit+close; extracted pure `parse_ping_time()` + `check_isp_anomaly()` + `prune_old_rows()` helpers. Added `test_prober.py` (stdlib unittest, 7 cases).
    * M-002 `index.astro`: chart moved to time-typed x-axis with `[timestamp, value]` series (fixes series/axis desync on missing samples). Extracted `frontend/src/lib/status.mjs` (`evaluateStatus`, `applyPingBlockedOverride`) + `status.test.mjs` (node:test).
    * M-003: standardized rootless `systemctl --user` (WantedBy=default.target); `reload-daemon.sh` installs units to `~/.config/systemd/user`, sed-substitutes `REPO_ROOT`/`UV_BIN` at install; removed all `sudo`/`/etc/systemd/system` paths.
    * M-004: dropped unused `echarts` npm dep (CDN `@5.5.0` only), pinned Python 3.12, deleted `hello.py`, synced ARCHITECTURE/README/CLAUDE + new `backend/` and `frontend/src/lib` docs.
    * Two Code-QR rounds: 6 findings (2 MUST + 4 SHOULD) fixed — status tests, anomaly-multiplier comment, osascript quote-escaping, god-function split, install-time path derivation, guarded DB writes. Doc-QR passed.

16. **Local Deploy Automation**
    * `reload-daemon.sh` Linux branch now builds the frontend (`npm install && npm run build`) with a hard guard: aborts before touching services if `dist/server/entry.mjs` is missing.
    * Added `deploy-local.sh`: wrapper that runs `reload-daemon.sh` (build + deploy) then opens the dashboard (`xdg-open`/`open`).

17. **Live-Monitoring Defects (found + fixed on the running deployment)**
    * **Duplicate root daemon:** a leftover pre-migration system-level `isp-health.service` (root, `/etc/systemd/system/`) was co-writing stale-network garbage (`192.168.1.1` / `send`) into the shared DB alongside the new rootless unit. Disabled + removed via sudo → single writer confirmed.
    * **Status-card flicker:** the `500` failure sentinel was inflating the rolling average, flipping ping-blocked-but-healthy targets to red "High Latency"; `evaluateStatus` now averages only successful (`< 500`) samples.
    * **Timestamp format bug (silent, high-impact):** prober wrote `isoformat()` (`T`/`+00:00`) but SQLite `datetime('now')` uses space format — lexicographic mismatch broke every `datetime()` comparison. Retention prune was a **no-op** (DB grew unbounded to ~79k rows) and the frontend "last 3 hours" query returned ~1.5 days (9,549 rows). Fixed: prober writes SQLite-canonical UTC (`strftime('%Y-%m-%d %H:%M:%S')`); `index.astro` parses as UTC; one-time migration normalized all 79,428 existing rows and the now-working prune trimmed pre-30-day rows. Verified: 3h window 9,549 → 1,302, single-writer 30s cadence restored.

---

## Manual Effort Estimation

If a single web developer were to code this entire system by hand from start to finish (including debugging, documentation, and environment setup), the estimated effort would be roughly **8 to 11 hours (1 to 1.5 full working days)**.

**Breakdown of Manual Tasks:**
* **Environment Setup & Backend Prober (2-3 hours):** Researching traceroutes to bypass double NAT, handling subprocess outputs in Python, structuring the SQLite schema, and writing the rolling average anomaly detection.
* **Astro SSR Setup & ECharts Integration (2-3 hours):** Scaffolding the framework, setting up the Node SSR adapter, querying SQLite natively inside Astro components, and mapping the data array into the ECharts syntax.
* **UI/UX Refinements (2 hours):** Writing custom CSS for the dark theme, designing the "Don't Make Me Think" status banner logic, styling the legends, and polishing the chart gradients/smoothing.
* **macOS System Integration (1-1.5 hours):** Figuring out the syntax to trigger Apple Notifications from Python without heavily relying on third-party libraries, and crafting a valid XML `launchd` plist file for background services.
* **PWA Conversion & Network Sharing (1 hour):** Creating the SVG icon, mapping the PWA manifest, and adjusting Vite config to listen on `0.0.0.0`.
* **Testing & Edge Cases (1-1.5 hours):** Debugging missed alerts during complete network disconnections (`-1.0` logic) and handling process-relative file paths for SQLite.
