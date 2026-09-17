---
key: token_workflow_confirmed_21-Jun-2026
date: 21-Jun-2026
type: memory
---

# Monday Morning Token Workflow (Confirmed 21-Jun-2026)

- **PC manual step**: NO (Normally) — Headless, browserless token generation via TOTP runs automatically on the VM at 08:15 IST daily. PC manual script (`deploy\zerodha_morning.bat` or `.ps1`) is only required as a fallback if the automated refresh fails. Fallback window: 08:15 - 09:14 IST.
- **VM auto step**: The token-watcher systemd service (`token-watcher.service`) polls every 30 seconds and automatically starts the `trading-system.service` once a fresh token is detected.
- **Pre-flight Phase A**: Runs at 08:30 IST via cron, catching a missing/stale token via `kite_token_file_exists` + `kite_token_fresh_today`. It is alert-only on failure but will attempt an auto-fix by running the token refresh script.
- **Browserless auto-token**: DONE (Implemented in v2.0 under FIX-187/FIX-135, active daily via VM cron).
