# frontend/src/lib/

Shared frontend utility modules for status evaluation and the route ladder.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `status.mjs` | `evaluateStatus` (latency-to-status classification) and `applyPingBlockedOverride` (DNS-healthy false-positive guard) | Modifying status thresholds, debugging offline/healthy classification, adding tests |
| `status.test.mjs` | Node test runner cases for `evaluateStatus` and `applyPingBlockedOverride` | Adding or verifying status logic tests |
| `geo.mjs` | `lookupHopGeo` (IP→hop entry by exact then CIDR-prefix match), `latencyToColor` (heat color at status.mjs thresholds + offline sentinel), `tierColor` (LAN/ISP/external palette) for the Route Ladder | Changing hop resolution, latency colors, or tier colors |
| `geo.test.mjs` | Node test runner cases for `lookupHopGeo`, `latencyToColor`, `tierColor` | Adding or verifying ladder helper tests |
| `hop-geo.json` | Curated IP/CIDR→{lat,lon,label,tier} table for this route's public hops (regenerate with `backend/geo_seed.py`) | Adding hops, correcting labels, or changing a hop's tier |
