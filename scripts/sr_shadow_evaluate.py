"""
scripts/sr_shadow_evaluate.py — S&R SHADOW v1.3 EOD counterfactual evaluator (§8).

Runs AFTER the session, on the TESTING VM only, from a hand-added crontab line
(never the canonical crontab). For the target date it:
  1. reconciles coverage: every screener-PASSED signal of the date vs the durable
     spool (a missing capture is COUNTED, never silently absent — addendum §4.1);
  2. fills §8 outcomes for each decided, not-yet-evaluated row from BROKER
     5-minute (confirming candle; never synthesised) and 1-minute candles;
  3. records the later admission outcome (signals.status) as diagnostic metadata;
  4. writes one evaluation_runs row with coverage + addendum §4.5 statistics and
     prints the same JSON to stdout.

Reads trading_system.db READ-ONLY (sqlite URI mode=ro). Writes only
data_store/sr_shadow/sr_shadow.db. Places no order; touches no production table.
Idempotent: already-evaluated rows are never overwritten; a row whose broker
fetch failed is left unevaluated for the next run (exit code 2). Refuses to
evaluate today before 15:30 IST (exit code 3).

Usage: python scripts/sr_shadow_evaluate.py [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SESSION_OVER = time(15, 30)
CATCH_UP_DAYS = 7  # earlier dates with decided-but-unevaluated rows are evaluated too (outcomes only)


def _parse_args(argv):
    ap = argparse.ArgumentParser(description="S&R shadow v1.3 EOD evaluator (log-only)")
    ap.add_argument("--date", help="target trading date YYYY-MM-DD (default: today IST)")
    ap.add_argument("--dry-run", action="store_true", help="compute and print; write nothing")
    return ap.parse_args(argv)


def trading_db_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=1")
    return conn


def build_market_data(log) -> Tuple[Dict[str, int], Callable]:
    """(token_by_symbol, hist_fetch) using the SAME pacing as the service's fetch
    closure (rate_limiter.acquire("historical"))."""
    from dotenv import load_dotenv
    from kiteconnect import KiteConnect  # type: ignore[import]

    from broker.rate_limiter import RateLimiter
    from core.account_registry import primary_api_key
    from core.config_loader import load_all

    load_dotenv(ROOT / ".env")
    tok_path = ROOT / "data_store" / "session" / "zerodha_token.json"
    access = json.loads(tok_path.read_text(encoding="utf-8")).get("access_token")
    kite = KiteConnect(api_key=primary_api_key())
    kite.set_access_token(access)
    token_by_symbol = {i["tradingsymbol"]: int(i["instrument_token"]) for i in kite.instruments("NSE")}
    rl = RateLimiter(load_all(ROOT / "config").broker_limits)

    def hist_fetch(token, frm, to, interval):
        rl.acquire("historical")
        return kite.historical_data(instrument_token=token, from_date=frm, to_date=to, interval=interval)

    return token_by_symbol, hist_fetch


def run(*, target: date, now_fn: Callable[[], datetime], store, trading: sqlite3.Connection,
        market_data_builder: Callable[[], Tuple[Dict[str, int], Callable]], log,
        dry_run: bool = False, catch_up_days: int = CATCH_UP_DAYS) -> Tuple[int, dict]:
    from sr_detector.models import Candle
    from sr_shadow import params as P
    from sr_shadow.evaluator import evaluate_signal, outcome_statistics

    now = now_fn()
    if target == now.date() and now.time() < SESSION_OVER:
        return 3, {"target_date": target.isoformat(), "refused": "session not over (evaluate at/after 15:30 IST)"}

    # 1. coverage reconciliation (screener PASSED vs spool)
    passed = [r["signal_id"] for r in trading.execute(
        "SELECT DISTINCT r.signal_id FROM screener_results r JOIN signals s ON s.signal_id = r.signal_id "
        "WHERE r.status = 'PASSED' AND substr(s.received_at, 1, 10) = ? ORDER BY r.signal_id",
        (target.isoformat(),))]
    spooled = set(store.spooled_signal_ids())
    missing = [sid for sid in passed if sid not in spooled]
    coverage = {
        "screener_passed": len(passed),
        "spooled": len(passed) - len(missing),
        "missing_capture": len(missing),
        "missing_capture_signal_ids": missing,
        "spool_status_for_date": store.spool_counts(target.isoformat()),
    }

    # 2. outcomes — the target date plus any EARLIER date (within the catch-up window)
    #    that still holds decided-but-unevaluated rows (e.g. a worker backlog after a
    #    restart). Outcomes only; no decision is ever computed here.
    first = (target - timedelta(days=catch_up_days)).isoformat()
    eval_dates = sorted(set(store.unevaluated_dates(first, target.isoformat())) | {target.isoformat()})
    rows = [r for d in eval_dates for r in store.rows_for_date(d, only_unevaluated=True)]
    fetch_stats = {"distinct_symbol_dates": 0, "fetch_calls": 0, "fetch_failures": 0}
    token_by_symbol: Dict[str, int] = {}
    hist_fetch: Optional[Callable] = None
    if rows:
        try:
            token_by_symbol, hist_fetch = market_data_builder()
        except Exception as exc:  # noqa: BLE001
            log.error("sr_shadow_evaluate: market data unavailable: %s", exc)

    candles_by_key = {}
    for symbol, day_iso in sorted({(str(r["symbol"]), str(r["date"])) for r in rows}):
        fetch_stats["distinct_symbol_dates"] += 1
        token = token_by_symbol.get(symbol)
        if hist_fetch is None or token is None:
            fetch_stats["fetch_failures"] += 1
            continue
        day = date.fromisoformat(day_iso)
        frm = datetime.combine(day, time(9, 0))
        to = datetime.combine(day, time(15, 30))
        try:
            five = [Candle.from_kite(x) for x in (hist_fetch(token, frm, to, "5minute") or [])]
            fetch_stats["fetch_calls"] += 1
            one = [Candle.from_kite(x) for x in (hist_fetch(token, frm, to, "minute") or [])]
            fetch_stats["fetch_calls"] += 1
            candles_by_key[(symbol, day_iso)] = (five, one, now_fn())
        except Exception as exc:  # noqa: BLE001
            fetch_stats["fetch_failures"] += 1
            log.error("sr_shadow_evaluate: fetch failed for %s %s: %s", symbol, day_iso, exc)

    evaluated = 0
    left_unevaluated = 0
    for row in rows:
        data = candles_by_key.get((str(row["symbol"]), str(row["date"])))
        if data is None:
            left_unevaluated += 1
            continue
        five, one, fetched_at = data
        fields = evaluate_signal(row, five, one, fetched_at)
        sig = trading.execute("SELECT status, rejection_reason FROM signals WHERE signal_id = ?",
                              (row["signal_id"],)).fetchone()
        fields["admission_status"] = sig["status"] if sig else None
        fields["admission_reason"] = sig["rejection_reason"] if sig else None
        fields["evaluated_at"] = now_fn().isoformat()
        if dry_run or store.write_evaluation(str(row["signal_id"]), fields):
            evaluated += 1

    summary = {
        "target_date": target.isoformat(),
        "contract_version": P.CONTRACT_VERSION,
        "dry_run": bool(dry_run),
        "coverage": coverage,
        "dates_evaluated": eval_dates,
        "rows_evaluated_this_run": evaluated,
        "rows_left_unevaluated": left_unevaluated,
        "fetch": fetch_stats,
        "statistics": outcome_statistics(store.rows_for_date(target.isoformat())),
    }
    if not dry_run:
        store.record_run(now_fn().isoformat(), target.isoformat(), summary)
    return (2 if left_unevaluated else 0), summary


def main(argv=None) -> int:
    args = _parse_args(argv)

    from core.logger import get_logger
    from core.time_authority import now_ist
    from sr_shadow.store import open_store

    log = get_logger("sr_shadow_evaluate")
    target = date.fromisoformat(args.date) if args.date else now_ist().date()
    store = open_store(ROOT / "data_store" / "sr_shadow")
    trading = trading_db_readonly(ROOT / "data_store" / "trading_system.db")
    rc, summary = run(target=target, now_fn=now_ist, store=store, trading=trading,
                      market_data_builder=lambda: build_market_data(log), log=log, dry_run=args.dry_run)
    print(json.dumps(summary, sort_keys=True, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
