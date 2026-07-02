# backend

## Overview

Single-file Python daemon that pings three network layers every 30 seconds and writes latency measurements to a shared SQLite file. The design minimizes dependencies and requires no root privileges.

## Design Decisions

**WAL mode and busy_timeout (DL-005)**: The prober (writer) and the Astro SSR dashboard (reader) share one SQLite file. Default rollback-journal mode surfaces SQLITE_BUSY under concurrent access. WAL lets readers and the single writer proceed without contention; busy_timeout absorbs brief lock overlap on heavy pages.

**30-day retention, hourly cadence (DL-001)**: The DB grows at approximately 8.6k rows/day. A periodic DELETE (every 120 cycles, roughly one hour) keeps the working set bounded without per-cycle write amplification. The prune runs under WAL so readers are unaffected.

**subprocess argv alerts, no shell (DL-004)**: `send_alert` passes an argv list to `subprocess.run` with `shell=False`. Alert messages contain emoji and parentheses; shell-interpolated strings corrupt or fail on these characters.

**SIGTERM/SIGINT handler (DL-007)**: systemd sends SIGTERM on `systemctl stop`. Without a handler the process is killed mid-cycle, risking an uncommitted write and a WAL recovery on next start. The handler commits, closes the connection, and exits cleanly.

**Anomaly check every warm cycle (DL-006)**: The original code evaluated the moving-average spike condition only on the cycle that trimmed the window, suppressing alerts during steady-state operation. The fix separates trimming from checking: once the window holds at least 20 samples, the spike test runs on every cycle.

**parse_ping_time extracted (DL-012)**: Ping-output parsing was inline in `measure_latency`. Extracting it to a module-level function lets `test_prober.py` unit-test the highest-risk logic (string parsing) without invoking subprocess.

## Invariants

- `latency_ms == -1.0` is the canonical failure sentinel written by the prober. The frontend maps it to 500 for visual rendering; do not change this value.
- The TCP socket fallback (port 53 then 80 via `tcp_ping`) runs only when the native ping binary fails entirely, typically on ICMP-blocked networks.
- The prober is the sole writer to `network_metrics.db`. The frontend is read-only.
- The anomaly window is 20 samples (10 minutes at 30-second intervals). The spike threshold is 2x the moving average and greater than 50 ms.
