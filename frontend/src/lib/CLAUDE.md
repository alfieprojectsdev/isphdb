# frontend/src/lib/

Shared frontend utility modules for status evaluation.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `status.mjs` | `evaluateStatus` (latency-to-status classification) and `applyPingBlockedOverride` (DNS-healthy false-positive guard) | Modifying status thresholds, debugging offline/healthy classification, adding tests |
| `status.test.mjs` | Node test runner cases for `evaluateStatus` and `applyPingBlockedOverride` | Adding or verifying status logic tests |
