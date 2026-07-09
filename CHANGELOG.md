# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-09

First tagged release. A local-first network-health monitor that isolates LAN vs ISP-gateway
vs internet-backbone problems, with a live SSR dashboard.

### Added
- **Prober daemon** (`backend/prober.py`): 30s ICMP polling of three auto-detected targets
  (Local Router, ISP Gateway, External DNS) with TCP socket fallback when ICMP is blocked,
  WAL SQLite storage, 30-day retention pruning, and rolling anomaly detection.
- **Native OS alerts** via `osascript` (macOS) / `notify-send` (Linux), with a debounced
  critical-outage guard requiring consecutive ISP+DNS failures before firing.
- **Periodic route capture**: full traceroute-hop path recorded into a new `traceroute_hops`
  table every ~5 minutes (public hops only).
- **SSR dashboard** (`frontend/`, Astro + ECharts): 3-hour latency chart reading the SQLite
  DB directly at request time; 30s auto-reload; LAN-accessible; PWA-installable.
- **Route Ladder**: landscape home→internet hop path, one rung per network layer, colored
  by tier (LAN/ISP/external) with live per-hop latency — including the private Local Router
  and ISP Gateway hops. Pure SSR, no client JS.
- **Status rail**: compact Overall + per-layer (Home Router / ISP Gateway / Internet)
  green/yellow/red status tiles.
- **Sentinel markLine**: red "Offline (packet loss)" reference line on the chart at 500ms,
  shown only when a target is currently failing.
- Rootless service units for both components (systemd `--user`, launchd).

### Fixed
- `get_isp_gateway()` could latch a non-IP token (e.g. `"send"` from a transient tracepath
  `send failed` line) as the ISP gateway, making that target read 100% packet loss for the
  whole run. Hops are now validated as dotted-quad IPv4 before use.

### Design notes
- Chart series use a neutral categorical palette (blue/purple/teal) so line color denotes
  identity, not health — green/yellow/red is reserved for actual status (rail + latency).
- An earlier geographic route map was dropped in favor of the Route Ladder: every public
  hop on a typical route sits in one metro, so geography discriminated nothing.

[0.1.0]: https://github.com/alfieprojectsdev/isphdb/releases/tag/v0.1.0
