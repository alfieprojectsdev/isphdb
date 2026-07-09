# frontend/src/lib/

Shared frontend utility modules for status evaluation and the hop-geo map.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `status.mjs` | `evaluateStatus` (latency-to-status classification) and `applyPingBlockedOverride` (DNS-healthy false-positive guard) | Modifying status thresholds, debugging offline/healthy classification, adding tests |
| `status.test.mjs` | Node test runner cases for `evaluateStatus` and `applyPingBlockedOverride` | Adding or verifying status logic tests |
| `geo.mjs` | `lookupHopGeo` (IP→{lat,lon,label} by exact then CIDR-prefix match) and `latencyToColor` (heat color, status.mjs thresholds + offline sentinel) for the Route Geography panel | Changing hop→geo resolution or map heat colors |
| `geo.test.mjs` | Node test runner cases for `lookupHopGeo` and `latencyToColor` | Adding or verifying geo helper tests |
| `hop-geo.json` | Curated IP/CIDR→{lat,lon,label} table for this route's public hops (regenerate with `backend/geo_seed.py`) | Adding hops or correcting coordinates/labels |
