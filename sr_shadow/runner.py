"""
sr_shadow/runner.py — the log-only runtime: durable capture + background worker.

CAPTURE (signal path, synchronous, never raises): the screener-pass snapshot is
written to the durable spool BEFORE control returns to the signal path (addendum
§4.1). That write is the ONLY work on the signal path; historical fetching and
the structural decision run on one background worker. A capture that cannot be
written is logged at ERROR and counted; the EOD evaluator's coverage
reconciliation against screener_results then reports it as missing.

WORKER: drains PENDING spool rows oldest-first, computes the decision row with
sr_shadow.pipeline, and writes it atomically. Transient failures retry with
back-off; after max attempts the spool row is FAILED (counted, never silent).

CACHE (addendum §4.2): RAW daily candles only, keyed (symbol, as-of date). A zone
map, a validity result or a decision is NEVER cached — the map is rebuilt per
signal (§0.6). Every broker call goes through the injected, rate-limited
historical fetch closure (main.py _make_sr_fetch_fn → rate_limiter "historical").

Shadow gates nothing: no order, no reservation, no score, no status write.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from core.effect_telemetry import handle as _effect_handle
from sr_shadow import params as P
from sr_shadow.bars import years_before
from sr_shadow.calendar import TradingCalendar
from sr_shadow.pipeline import compute_decision_row
from sr_shadow.store import ShadowStore

_DAY_CHUNK_DAYS = 1000  # historical 'day' request window (well inside the broker's per-request span)


class MarketDataUnavailable(RuntimeError):
    """No market-data kite handle: never turned into a DATA_UNAVAILABLE decision."""


class DailyHistorySource:
    def __init__(self, fetch_fn: Callable, instrument_cache, market_data_available: bool,
                 max_entries: int = 512) -> None:
        self._fetch_fn = fetch_fn
        self._ic = instrument_cache
        self._available = bool(market_data_available)
        self._cache: "OrderedDict[Tuple[str, date], list]" = OrderedDict()
        self._max = int(max_entries)
        self._lock = threading.Lock()
        self.stats = {"cache_hits": 0, "cache_misses": 0, "fetch_calls": 0}

    def completed_daily_raw(self, symbol: str, decision_date: date) -> list:
        """Raw daily candles dated [decision_date − 5y, decision_date − 1]."""
        from sr_detector.models import Candle

        key = (symbol, decision_date)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                self.stats["cache_hits"] += 1
                return list(hit)
            self.stats["cache_misses"] += 1
        if not self._available or self._fetch_fn is None:
            raise MarketDataUnavailable("no market-data kite handle")
        token = int(self._ic.get_by_symbol(symbol).instrument_token)
        start = years_before(decision_date, P.HISTORY_YEARS)
        end = decision_date - timedelta(days=1)
        candles: list = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=_DAY_CHUNK_DAYS - 1), end)
            rows = self._fetch_fn(token, datetime.combine(cursor, time(0, 0)),
                                  datetime.combine(chunk_end, time(23, 59, 59)), "day")
            with self._lock:
                self.stats["fetch_calls"] += 1
            candles.extend(Candle.from_kite(r) for r in (rows or []))
            cursor = chunk_end + timedelta(days=1)
        with self._lock:
            self._cache[key] = list(candles)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)
        return candles


class SrShadowService:
    def __init__(
        self,
        *,
        store: ShadowStore,
        history: DailyHistorySource,
        calendar: TradingCalendar,
        calibration: P.Calibration,
        instrument_cache,
        signal_timestamp_fn: Callable[[str], Optional[datetime]],
        logger,
        now_fn: Callable[[], datetime],
        poll_interval_sec: float = 2.0,
        max_attempts: int = 5,
        retry_backoff_sec: float = 60.0,
    ) -> None:
        self._store = store
        self._history = history
        self._calendar = calendar
        self._calibration = calibration
        self._ic = instrument_cache
        self._signal_ts_fn = signal_timestamp_fn
        self._log = logger
        self._now = now_fn
        self._poll = float(poll_interval_sec)
        self._max_attempts = int(max_attempts)
        self._backoff = float(retry_backoff_sec)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fx_write = _effect_handle("sr_shadow")
        self._counter_lock = threading.Lock()
        self.counters = {"captured": 0, "capture_duplicates": 0, "capture_failures": 0,
                         "rows_written": 0, "rows_existing": 0, "attempt_failures": 0,
                         "spool_failed": 0, "invariant_violations": 0}

    # ── signal path ─────────────────────────────────────────────────────────
    def capture(self, snapshot: Dict[str, object]) -> None:
        """Durable spool write before returning. Never raises."""
        try:
            captured_at = self._now().isoformat()
            snap = dict(snapshot)
            snap["captured_at"] = captured_at
            inserted = self._store.spool_insert(str(snap["signal_id"]), captured_at, snap)
            with self._counter_lock:
                self.counters["captured" if inserted else "capture_duplicates"] += 1
            if not inserted:
                self._safe_log("info", "sr_shadow.capture_duplicate signal_id=%s (first capture kept)",
                               snap["signal_id"])
        except Exception as exc:  # noqa: BLE001 — shadow must never touch the pipeline
            with self._counter_lock:
                self.counters["capture_failures"] += 1
            self._safe_log("error", "sr_shadow.capture_failed signal_id=%s error=%s",
                           snapshot.get("signal_id"), exc)

    # ── worker ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="sr-shadow-worker", daemon=True)
        self._thread.start()
        self._safe_log("info", "sr_shadow: worker started (contract=%s schema=%s db=%s)",
                       P.CONTRACT_VERSION, P.SCHEMA_VERSION, self._store.path)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._safe_log("info", "sr_shadow: worker stopped counters=%s history=%s",
                       json.dumps(self.counters), json.dumps(self._history.stats))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.drain_once()
            except Exception as exc:  # noqa: BLE001
                self._safe_log("error", "sr_shadow: drain error=%s", exc)
                worked = 0
            if not worked:
                self._stop.wait(self._poll)

    def drain_once(self, limit: int = 20) -> int:
        rows = self._store.spool_pending(self._now().isoformat(), limit=limit)
        for r in rows:
            if self._stop.is_set():
                break
            self.process_spool_row(r)
        return len(rows)

    def process_spool_row(self, spool_row) -> None:
        signal_id = spool_row["signal_id"]
        try:
            snapshot = json.loads(spool_row["snapshot_json"])
            signal_ts = self._signal_ts_fn(signal_id)
            if signal_ts is None:
                raise LookupError(f"signals.received_at not found for {signal_id}")
            symbol = str(snapshot["symbol"])
            tick_size = float(self._ic.get_by_symbol(symbol).tick_size)
            raw = self._history.completed_daily_raw(symbol, signal_ts.date())
            row = compute_decision_row(
                snapshot, signal_ts, raw, self._calendar, self._calibration, tick_size,
                decided_at=self._now().isoformat(),
                on_invariant_violation=self._on_invariant_violation,
            )
            inserted = self._store.complete_decision(signal_id, row, self._now().isoformat())
            with self._counter_lock:
                self.counters["rows_written" if inserted else "rows_existing"] += 1
            if inserted:
                self._fx_write.inc()
        except Exception as exc:  # noqa: BLE001
            now = self._now()
            status = self._store.spool_record_failure(
                signal_id, f"{type(exc).__name__}: {exc}", now.isoformat(),
                (now + timedelta(seconds=self._backoff)).isoformat(), self._max_attempts,
            )
            with self._counter_lock:
                self.counters["attempt_failures"] += 1
                if status == "FAILED":
                    self.counters["spool_failed"] += 1
            level = "error" if status == "FAILED" else "warning"
            self._safe_log(level, "sr_shadow.process_failed signal_id=%s status=%s error=%s",
                           signal_id, status, exc)

    def _on_invariant_violation(self, detail: dict) -> None:
        with self._counter_lock:
            self.counters["invariant_violations"] += 1
        self._safe_log("error", "sr_shadow.stop_invariant_violated %s", json.dumps(detail, sort_keys=True))

    def _safe_log(self, level: str, msg: str, *args) -> None:
        try:
            getattr(self._log, level)(msg, *args)
        except Exception:  # noqa: BLE001
            pass


def build_sr_shadow(
    *,
    config,
    fetch_fn: Optional[Callable],
    market_data_available: bool,
    instrument_cache,
    state_store,
    special_sessions: Optional[dict],
    logger,
    now_fn: Callable[[], datetime],
    config_dir: Path = Path("config"),
    data_dir: Path = Path("data_store/sr_shadow"),
) -> SrShadowService:
    """Wire the shadow from `system.sr_shadow` config + injected collaborators."""
    from sr_shadow.store import open_store

    calibration = P.Calibration.from_config(config)
    calendar = TradingCalendar.from_config_dir(Path(config_dir), special_sessions=special_sessions)
    store = open_store(Path(data_dir))
    history = DailyHistorySource(fetch_fn, instrument_cache, market_data_available)

    def _signal_ts(signal_id: str) -> Optional[datetime]:
        row = state_store.fetch_one("SELECT received_at FROM signals WHERE signal_id = ?", (signal_id,))
        if row is None or row["received_at"] is None:
            return None
        return datetime.fromisoformat(str(row["received_at"]))

    return SrShadowService(
        store=store, history=history, calendar=calendar, calibration=calibration,
        instrument_cache=instrument_cache, signal_timestamp_fn=_signal_ts, logger=logger,
        now_fn=now_fn, poll_interval_sec=float(config.worker_poll_interval_sec),
        max_attempts=int(config.worker_max_attempts),
        retry_backoff_sec=float(config.worker_retry_backoff_sec),
    )
