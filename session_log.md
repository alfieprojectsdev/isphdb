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

## Manual Effort Estimation

If a single web developer were to code this entire system by hand from start to finish (including debugging, documentation, and environment setup), the estimated effort would be roughly **8 to 11 hours (1 to 1.5 full working days)**.

**Breakdown of Manual Tasks:**
* **Environment Setup & Backend Prober (2-3 hours):** Researching traceroutes to bypass double NAT, handling subprocess outputs in Python, structuring the SQLite schema, and writing the rolling average anomaly detection.
* **Astro SSR Setup & ECharts Integration (2-3 hours):** Scaffolding the framework, setting up the Node SSR adapter, querying SQLite natively inside Astro components, and mapping the data array into the ECharts syntax.
* **UI/UX Refinements (2 hours):** Writing custom CSS for the dark theme, designing the "Don't Make Me Think" status banner logic, styling the legends, and polishing the chart gradients/smoothing.
* **macOS System Integration (1-1.5 hours):** Figuring out the syntax to trigger Apple Notifications from Python without heavily relying on third-party libraries, and crafting a valid XML `launchd` plist file for background services.
* **PWA Conversion & Network Sharing (1 hour):** Creating the SVG icon, mapping the PWA manifest, and adjusting Vite config to listen on `0.0.0.0`.
* **Testing & Edge Cases (1-1.5 hours):** Debugging missed alerts during complete network disconnections (`-1.0` logic) and handling process-relative file paths for SQLite.
