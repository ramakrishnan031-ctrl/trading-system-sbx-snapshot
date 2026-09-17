# Backup Restore Drill Report - 2026-08-01

**Executed at:** 2026-08-01 03:00:01
**Expected schema version:** 45

## Backup Selected
- **File:** trading_system-2026-08-01.db
- **Size:** 170,868,736 bytes (163.0 MB)
- **Modified:** 2026-08-01 01:00:01

## Restore
- Restored to: `/tmp/backup_drill_y1dzatye/restore_test.db`
- Restored size: 170,868,736 bytes

## Integrity Check
- PRAGMA integrity_check: **PASSED**

## Schema Version
- Version 45: **MATCHES** (expected 45)

## Tables (45 found, 26 expected)
- All 26 expected tables present: **PASSED**
- Extra tables (informational): config_snapshots, control_tower_findings, control_tower_freshness, control_tower_runs, control_tower_status, control_tower_trends, daily_symbol_stats, eod_broker_reconciliation, excursion_reconstruction_runs, gtt_state, market_execution_context, order_execution_log, pb01_watchlist, preflight_autofix_log, preflight_check_results, preflight_runs, retest_state, sr_detector_results, trade_slippage_log

### Row Counts
| Table | Rows |
|-------|------|
| capital_snapshot | 0 |
| config_snapshots | 23 |
| control_tower_findings | 22 |
| control_tower_freshness | 150 |
| control_tower_runs | 25 |
| control_tower_status | 25 |
| control_tower_trends | 25 |
| cron_heartbeat | 3,552 |
| daily_symbol_stats | 0 |
| eod_broker_reconciliation | 16 |
| eod_squareoff_log | 32 |
| eod_verification | 31 |
| excursion_reconstruction_runs | 25 |
| fm_ledger | 2,797 |
| fno_ban | 13 |
| gate_state | 0 |
| gtt_state | 0 |
| innings | 322 |
| kill_switch_state | 1 |
| market_execution_context | 362 |
| order_execution_log | 362 |
| orders | 805 |
| pb01_watchlist | 84 |
| pnl_reconciliation | 16 |
| position_reconciliation | 10 |
| preflight_autofix_log | 0 |
| preflight_check_results | 0 |
| preflight_runs | 0 |
| reconciliation_log | 7,804 |
| retest_state | 0 |
| schema_meta | 1 |
| screener_results | 49,209 |
| session | 1 |
| shadow_trades | 0 |
| signals | 72,458 |
| smart_tgt_state | 0 |
| sr_detector_results | 270 |
| strategy_metrics | 314 |
| system_events | 179 |
| telegram_alerts | 0 |
| trade_excursions | 157 |
| trade_journal | 145 |
| trade_slippage_log | 181 |
| trades | 478 |
| webhook_audit | 127,272 |

## Foreign Key Integrity
- No orphaned foreign keys: **PASSED**

## WAL Checkpoint
- Checkpoint: **CLEAN**

## Sample Queries
- closed_trades: 161
- latest_signal_date: 2026-07-31
- open_trades: 0
- total_orders: 805

## Verdict
**DRILL PASSED** -- backup restoration verified successfully.
