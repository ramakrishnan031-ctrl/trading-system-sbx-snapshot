# Backup Restore Drill Report - 2026-09-01

**Executed at:** 2026-09-01 03:00:02
**Expected schema version:** 45

## Backup Selected
- **File:** trading_system-2026-09-01.db
- **Size:** 447,414,272 bytes (426.7 MB)
- **Modified:** 2026-09-01 01:00:02

## Restore
- Restored to: `/tmp/backup_drill_c97g_2j8/restore_test.db`
- Restored size: 447,414,272 bytes

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
| config_snapshots | 44 |
| control_tower_findings | 27 |
| control_tower_freshness | 276 |
| control_tower_runs | 46 |
| control_tower_status | 46 |
| control_tower_trends | 46 |
| cron_heartbeat | 5,998 |
| daily_symbol_stats | 0 |
| eod_broker_reconciliation | 37 |
| eod_squareoff_log | 52 |
| eod_verification | 52 |
| excursion_reconstruction_runs | 46 |
| fm_ledger | 4,715 |
| fno_ban | 56 |
| gate_state | 0 |
| gtt_state | 37 |
| innings | 322 |
| kill_switch_state | 1 |
| market_execution_context | 557 |
| order_execution_log | 557 |
| orders | 1,266 |
| pb01_watchlist | 666 |
| pnl_reconciliation | 37 |
| position_reconciliation | 18 |
| preflight_autofix_log | 0 |
| preflight_check_results | 0 |
| preflight_runs | 0 |
| reconciliation_log | 7,902 |
| retest_state | 0 |
| schema_meta | 1 |
| screener_results | 158,044 |
| session | 1 |
| shadow_trades | 0 |
| signals | 191,347 |
| smart_tgt_state | 0 |
| sr_detector_results | 562 |
| strategy_metrics | 573 |
| system_events | 245 |
| telegram_alerts | 0 |
| trade_excursions | 272 |
| trade_journal | 245 |
| trade_slippage_log | 296 |
| trades | 809 |
| webhook_audit | 208,459 |

## Foreign Key Integrity
- No orphaned foreign keys: **PASSED**

## WAL Checkpoint
- Checkpoint: **CLEAN**

## Sample Queries
- closed_trades: 265
- latest_signal_date: 2026-08-31
- open_trades: 0
- total_orders: 1266

## Verdict
**DRILL PASSED** -- backup restoration verified successfully.
