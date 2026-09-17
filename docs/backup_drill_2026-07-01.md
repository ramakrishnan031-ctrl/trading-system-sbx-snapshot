# Backup Restore Drill Report - 2026-07-01

**Executed at:** 2026-07-01 03:00:01
**Expected schema version:** 40

## Backup Selected
- **File:** trading_system-2026-07-01.db
- **Size:** 204,566,528 bytes (195.1 MB)
- **Modified:** 2026-07-01 01:00:01

## Restore
- Restored to: `/tmp/backup_drill_te2g1a30/restore_test.db`
- Restored size: 204,566,528 bytes

## Integrity Check
- PRAGMA integrity_check: **PASSED**

## Schema Version
- Version 40: **MATCHES** (expected 40)

## Tables (41 found, 26 expected)
- All 26 expected tables present: **PASSED**
- Extra tables (informational): control_tower_findings, control_tower_freshness, control_tower_runs, control_tower_status, control_tower_trends, excursion_reconstruction_runs, gtt_state, market_execution_context, order_execution_log, preflight_autofix_log, preflight_check_results, preflight_runs, retest_state, sr_detector_results, trade_slippage_log

### Row Counts
| Table | Rows |
|-------|------|
| capital_snapshot | 0 |
| control_tower_findings | 3 |
| control_tower_freshness | 12 |
| control_tower_runs | 2 |
| control_tower_status | 2 |
| control_tower_trends | 2 |
| cron_heartbeat | 929 |
| eod_squareoff_log | 12 |
| eod_verification | 8 |
| excursion_reconstruction_runs | 2 |
| fm_ledger | 853 |
| fno_ban | 3 |
| gate_state | 0 |
| gtt_state | 0 |
| innings | 102 |
| kill_switch_state | 1 |
| market_execution_context | 72 |
| order_execution_log | 72 |
| orders | 251 |
| pnl_reconciliation | 0 |
| position_reconciliation | 0 |
| preflight_autofix_log | 0 |
| preflight_check_results | 0 |
| preflight_runs | 0 |
| reconciliation_log | 7,758 |
| retest_state | 0 |
| schema_meta | 1 |
| screener_results | 64,740 |
| session | 1 |
| shadow_trades | 0 |
| signals | 75,928 |
| smart_tgt_state | 0 |
| sr_detector_results | 29 |
| strategy_metrics | 53 |
| system_events | 93 |
| telegram_alerts | 0 |
| trade_excursions | 15 |
| trade_journal | 26 |
| trade_slippage_log | 36 |
| trades | 173 |
| webhook_audit | 46,392 |

## Foreign Key Integrity
- No orphaned foreign keys: **PASSED**

## WAL Checkpoint
- Checkpoint: **CLEAN**

## Sample Queries
- closed_trades: 42
- latest_signal_date: 2026-06-30
- open_trades: 0
- total_orders: 251

## Verdict
**DRILL PASSED** -- backup restoration verified successfully.
