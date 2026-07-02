# ISP Health Dashboard — Improvement Plan

**Date:** 2026-06-29
**Scope:** `backend/prober.py`, `frontend/src/pages/index.astro`, repo hygiene (deps, docs, services)
**Out of scope:** stack rewrite, API layer, multi-host/cloud deploy, auth, splitting the single-file SQLite design

## Problem

`isphdb` is a local-first home ISP health monitor: a rootless Python prober pings three network layers every 30s into a single SQLite file, and a decoupled Astro SSR dashboard reads that file at request time to render an ECharts view. It works, but carries correctness and robustness defects:

- Frontend **desyncs series from the time axis** when any target is missing a sample for an interval (x-axis built from a shared `Set`, series pushed independently).
- Notifications shell out via `os.system` with an **interpolated message** (shell-injection smell).
- DB opened **without WAL** while the SSR process reads concurrently → possible `SQLITE_BUSY`.
- ISP anomaly check **only runs on window-overflow cycles** (moving-average + threshold computed inside the `pop` block).
- DB **grows unbounded** (already 32MB; UI shows only last 3h).
- Prober has **no graceful shutdown**; connection never closed.
- Bundled `echarts` dep unused (CDN loads 5.5.0); `hello.py` dead scaffold; `requires-python >=3.11` vs documented 3.12; docs (`ARCHITECTURE.md`) stale re: TCP fallback; README/`reload-daemon.sh` use `sudo` system services contradicting the no-root design.

## Approach

Harden incrementally in priority waves — no stack change, no API layer, no DB split.

- **Wave 1 (parallel, disjoint file sets):** correctness/robustness across backend prober, frontend axis, and service standardization.
- **Wave 2:** repo hygiene + documentation sync.

### Confirmed policy decisions
- **Retention:** prune rows older than **30 days** inside the prober loop (hourly cadence).
- **Services:** standardize on **rootless `systemctl --user`** units; eliminate all `sudo`/system-level paths.

---

## Wave 1 — Correctness & Robustness

### M-001 — Backend prober correctness and robustness
**Files:** `backend/prober.py`, `backend/test_prober.py`

| Change | Location | What |
|---|---|---|
| CI-001 | `send_alert` | Replace `os.system` f-string with `subprocess.run` argv list (no shell). Message passed as discrete argv element → no metachar evaluation. *(DL-004)* |
| CI-002 | `init_db` | Set `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout` (few sec) so writer + readonly SSR readers run concurrently without `SQLITE_BUSY`. *(DL-005)* |
| CI-003 | `run_prober` | Restructure ISP anomaly block: append → trim to last N as separate step → once window warm, compute moving avg + evaluate spike **every cycle** (not only on pop). *(DL-006)* |
| CI-004 | `run_prober` | Hourly-cadence `DELETE` of rows older than 30 days + commit; coarse cadence avoids per-cycle write overhead. *(DL-001)* |
| CI-005 | `run_prober` | SIGINT/SIGTERM handling: commit pending writes, close connection, clean exit. *(DL-007)* |
| CI-006 | `measure_latency` | Extract ping-output time parsing into importable pure helper (returns float or sentinel) for unit testing. *(DL-012)* |
| CI-007 | `test_prober.py` | stdlib `unittest` cases: parse helper (valid→float, missing→sentinel, malformed→no raise) + status helper. Runs via `python -m unittest`. *(DL-012)* |

**Acceptance:** alert with shell metachars renders literal (no shell eval); `PRAGMA journal_mode` reports `wal`, no `SQLITE_BUSY` on concurrent read; warm window + single 3× spike >50ms fires exactly one alert; no row older than 30 days survives, count stabilizes; SIGTERM leaves committed DB needing no recovery; `test_prober.py` green.

### M-002 — Frontend chart time-axis alignment
**Files:** `frontend/src/pages/index.astro`, `frontend/src/lib/status.mjs`

| Change | Location | What |
|---|---|---|
| CI-001 | `index.astro` | Build each ECharts series as explicit `[timestamp, value]` point pairs (failures still →500); configure **time-typed xAxis**; remove shared category `Set`. Fixes desync. *(DL-003)* |
| CI-002 | `status.mjs::evaluateStatus` | Extract latency→status classification + DNS-reachable false-positive override into pure importable functions (used by `index.astro` + tests); preserve current behavior. *(DL-003, DL-012)* |

**Acceptance:** with one target missing a sample, remaining series still plot every point at its true timestamp; dropped ping still renders red 500ms spike; status cards + DNS override give identical classifications to current behavior on complete data.

### M-003 — Rootless systemd service standardization
**Files:** `reload-daemon.sh`, `backend/isp-health.service`, `frontend/isp-health-frontend.service`

| Change | Location | What |
|---|---|---|
| CI-001 | `reload-daemon.sh` | Rewrite Linux branch: install units into user systemd dir, manage via `systemctl --user` (daemon-reload, enable --now, stop on reload). No `sudo`, no `/etc/systemd/system`. *(DL-002)* |
| CI-002 | `isp-health.service` | User-level unit (`WantedBy=default.target`), WorkingDirectory + ExecStart at canonical repo path, `uv run` prober. *(DL-002)* |
| CI-003 | `isp-health-frontend.service` | Confirm user-level unit binding `HOST=0.0.0.0 PORT=4321`, standalone node server from canonical path; added StandardOutput/StandardError to match backend logging. *(DL-002)* |

**Acceptance:** `reload-daemon.sh` on Linux as non-root installs + starts both via `systemctl --user` with no privilege prompt; `systemctl --user status` reports both active; paths resolve under canonical repo location.

---

## Wave 2 — Hygiene, Dependencies, Docs

### M-004 — Repo hygiene, dependency hardening, documentation sync
**Files:** `frontend/package.json`, `backend/pyproject.toml`, `backend/.python-version`, `backend/hello.py`, `ARCHITECTURE.md`, `README.md`, `CLAUDE.md`

| Change | Location | What |
|---|---|---|
| CI-001 | `package.json` | Remove unused `echarts` dep; CDN-loaded echarts is sole charting source. *(DL-008)* |
| CI-002 | `pyproject.toml` | `requires-python` → 3.12 series. *(DL-009)* |
| CI-003 | `.python-version` | Confirm reads `3.12` (already does). *(DL-009)* |
| CI-004 | `hello.py` | Delete unused uv-init scaffold. *(DL-011)* |
| CI-005 | `ARCHITECTURE.md` | Document TCP fallback (ICMP blocked), rootless `systemctl --user` workflow, 30-day retention, auto-detected targets; drop ICMP-only/system-level claims. *(DL-010)* |
| CI-006 | `README.md` | Setup commands → `systemctl --user` (no sudo); accurate TCP fallback; 30-day retention; auto-detected targets. *(DL-010)* |
| CI-007 | `CLAUDE.md` | Align architecture notes + commands with TCP fallback, rootless `--user`, 30-day retention. *(DL-010)* |

**Acceptance:** `npm install` resolves without echarts, dashboard still renders via CDN; `uv` resolves 3.12 with no `requires-python` warning; no `backend/hello.py`; docs contain no `sudo systemctl` and accurately state TCP fallback + 30-day retention.

---

## Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-001 | Time-typed axis may alter tick labels/smoothing vs category axis | Visually verify against current; keep smoothing config |
| R-002 | WAL leaves `-wal`/`-shm` sidecars; unclean kill recovers WAL | Acceptable; graceful shutdown (CI-005) minimizes |
| R-003 | Periodic DELETE may briefly contend with SSR reads | Coarse hourly cadence + busy_timeout absorbs |
| R-004 | `--user` units don't survive logout without lingering | Document `loginctl enable-linger $USER` |
| R-005 | Corrected anomaly flow changes alert timing; may surface alerts the bug suppressed | Expected/desired; note in changelog |

---

## Status

- Plan design QR: **PASS** (structural defects from a mid-run crash were repaired: duplicate milestone set removed, code-intent dedup, file-scope alignment).
- Code-diff QR gate: **not completed** — the final review subagent hit the monthly spend limit before writing its report. Diffs for all 19 intents are authored into `plan.json` but **un-reviewed**; treat them as draft. No source files were modified.

**Plan state:** `.claude/planner-state/planner-tiynwepo/plan.json`
