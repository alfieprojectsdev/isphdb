# frontend/src/lib

## Overview

Status evaluation functions extracted from `index.astro` for independent testability.

## Design Decisions

**Extraction rationale (DL-012)**: `evaluateStatus` and `applyPingBlockedOverride` were inline closures inside the Astro frontmatter of `index.astro`. The SSR context makes them untestable without a full build. Extracting them to `status.mjs` allows Node-native testing without a browser or bundler.

## Invariants

- `evaluateStatus` accepts both scalar latency values and `[timestamp, value]` pairs. The `.map(pt => Array.isArray(pt) ? pt[1] : pt)` step normalizes the time-axis point format used by `index.astro` after the M-002 chart alignment fix.
- The threshold ladder — `>= 500` maps to offline, `> 150` or avg `> 100` maps to bad, `> 75` or avg `> 60` maps to warn — must stay in sync with the values documented in `ARCHITECTURE.md`.
- `applyPingBlockedOverride` returns new status objects and does not mutate its inputs. The caller must `Object.assign` to apply overrides to the mutable status variables.
- The DNS-healthy override only fires when `dnsStatus.status` is `'good'` or `'warn'`. If DNS itself is offline, no override is applied.
