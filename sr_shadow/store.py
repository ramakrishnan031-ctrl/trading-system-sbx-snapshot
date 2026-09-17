"""
sr_shadow/store.py — the ONE authoritative S&R shadow dataset (R10).

A dedicated SQLite file under data_store/sr_shadow/, OUTSIDE the trading
database's migration chain, with its own explicit schema version. It is never a
production-path table and it never touches trading_system.db.

Tables:
  meta             schema_version / contract_version
  spool            the durable screener-pass snapshots (addendum §4.1): written
                   BEFORE the signal path returns; the worker drains it
  shadow_rows      one row per signal (§9 schema, sr_shadow/schema.py)
  evaluation_runs  one row per EOD evaluator run (coverage + §4.5 statistics)

Writes are atomic (one transaction each) and never silently overwrite: a
duplicate spool snapshot or decision row is refused, and the evaluator only
fills rows whose evaluated_at IS NULL.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sr_shadow import params as P
from sr_shadow import schema as S

DB_FILENAME = "sr_shadow.db"


class SrShadowSchemaMismatch(RuntimeError):
    """The on-disk sr_shadow.db was written by a different schema version."""


_SPOOL_DDL = """
CREATE TABLE IF NOT EXISTS spool (
    signal_id       TEXT PRIMARY KEY,
    captured_at     TEXT NOT NULL,
    snapshot_json   TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING','DONE','FAILED')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error      TEXT,
    updated_at      TEXT NOT NULL
)
"""

_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at       TEXT NOT NULL,
    target_date  TEXT NOT NULL,
    stats_json   TEXT NOT NULL
)
"""


def _rows_ddl() -> str:
    cols = ",\n    ".join(f'"{n}" {t}' for n, t in S.all_columns())
    return f"CREATE TABLE IF NOT EXISTS shadow_rows (\n    signal_id TEXT PRIMARY KEY,\n    {cols}\n)"


class ShadowStore:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False, timeout=10.0,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._init_schema()

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── schema ──────────────────────────────────────────────────────────────
    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if row is None:
                    self._conn.execute(_SPOOL_DDL)
                    self._conn.execute(_rows_ddl())
                    self._conn.execute(_RUNS_DDL)
                    self._conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                                       (str(P.SCHEMA_VERSION),))
                    self._conn.execute("INSERT INTO meta(key, value) VALUES('contract_version', ?)",
                                       (P.CONTRACT_VERSION,))
                elif int(row["value"]) != P.SCHEMA_VERSION:
                    raise SrShadowSchemaMismatch(
                        f"{self._path}: schema_version {row['value']} != expected {P.SCHEMA_VERSION} "
                        "(no silent migration; move the file aside deliberately)"
                    )
                else:
                    existing = [r["name"] for r in self._conn.execute("PRAGMA table_info(shadow_rows)")]
                    expected = ["signal_id"] + list(S.COLUMN_NAMES)
                    if existing != expected:
                        raise SrShadowSchemaMismatch(
                            f"{self._path}: shadow_rows columns differ from schema v{P.SCHEMA_VERSION}"
                        )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    # ── spool ───────────────────────────────────────────────────────────────
    def spool_insert(self, signal_id: str, captured_at: str, snapshot: dict) -> bool:
        """Durable INSERT (synchronous=FULL). False when the signal is already spooled
        (never overwritten — the first capture is immutable)."""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO spool(signal_id, captured_at, snapshot_json, status, attempts, updated_at) "
                    "VALUES(?, ?, ?, 'PENDING', 0, ?)",
                    (signal_id, captured_at, json.dumps(snapshot, sort_keys=True), captured_at),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def spool_pending(self, now_iso: str, limit: int = 20) -> List[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(
                "SELECT * FROM spool WHERE status='PENDING' "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                "ORDER BY captured_at, signal_id LIMIT ?",
                (now_iso, limit),
            ))

    def spool_record_failure(self, signal_id: str, error: str, now_iso: str,
                             next_attempt_at: Optional[str], max_attempts: int) -> str:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT attempts FROM spool WHERE signal_id=?", (signal_id,)).fetchone()
                attempts = (int(row["attempts"]) if row else 0) + 1
                status = "FAILED" if attempts >= max_attempts else "PENDING"
                self._conn.execute(
                    "UPDATE spool SET attempts=?, status=?, last_error=?, next_attempt_at=?, updated_at=? "
                    "WHERE signal_id=? AND status='PENDING'",
                    (attempts, status, error[:2000], next_attempt_at, now_iso, signal_id),
                )
                self._conn.execute("COMMIT")
                return status
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def spool_counts(self, date_prefix: Optional[str] = None) -> Dict[str, int]:
        with self._lock:
            if date_prefix:
                rows = self._conn.execute(
                    "SELECT status, COUNT(*) AS n FROM spool WHERE captured_at LIKE ? GROUP BY status",
                    (f"{date_prefix}%",))
            else:
                rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM spool GROUP BY status")
            return {r["status"]: int(r["n"]) for r in rows}

    def spooled_signal_ids(self) -> List[str]:
        with self._lock:
            return [r["signal_id"] for r in self._conn.execute("SELECT signal_id FROM spool")]

    # ── decision rows ───────────────────────────────────────────────────────
    def complete_decision(self, signal_id: str, row: Dict[str, object], now_iso: str) -> bool:
        """Atomically insert the decision row and mark the spool entry DONE. False
        when a row already exists (never overwritten; spool still marked DONE)."""
        unknown = set(row) - set(S.COLUMN_NAMES)
        if unknown:
            raise KeyError(f"unknown shadow_rows columns: {sorted(unknown)}")
        names = ["signal_id"] + list(S.COLUMN_NAMES)
        values = [signal_id] + [_to_sql(row.get(n)) for n in S.COLUMN_NAMES]
        placeholders = ", ".join("?" for _ in names)
        quoted = ", ".join(f'"{n}"' for n in names)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                inserted = True
                try:
                    self._conn.execute(f"INSERT INTO shadow_rows({quoted}) VALUES({placeholders})", values)
                except sqlite3.IntegrityError:
                    inserted = False
                self._conn.execute(
                    "UPDATE spool SET status='DONE', updated_at=?, last_error=? WHERE signal_id=?",
                    (now_iso, None if inserted else "ROW_ALREADY_EXISTS", signal_id),
                )
                self._conn.execute("COMMIT")
                return inserted
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def rows_for_date(self, date_iso: str, only_unevaluated: bool = False) -> List[Dict[str, object]]:
        sql = "SELECT * FROM shadow_rows WHERE date=?"
        if only_unevaluated:
            sql += " AND evaluated_at IS NULL"
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql + " ORDER BY signal_timestamp_used, signal_id", (date_iso,))]

    def unevaluated_dates(self, first_iso: str, last_iso: str) -> List[str]:
        """Dates in [first, last] that still hold decided-but-unevaluated rows."""
        with self._lock:
            return [r["date"] for r in self._conn.execute(
                "SELECT DISTINCT date FROM shadow_rows WHERE evaluated_at IS NULL AND date >= ? AND date <= ? "
                "ORDER BY date", (first_iso, last_iso))]

    def write_evaluation(self, signal_id: str, fields: Dict[str, object]) -> bool:
        """Fill evaluator-owned columns on a not-yet-evaluated row. False when the row
        was already evaluated (never overwritten)."""
        bad = set(fields) - set(S.EVALUATOR_COLUMNS)
        if bad:
            raise KeyError(f"evaluator may not write columns: {sorted(bad)}")
        sets = ", ".join(f'"{k}"=?' for k in fields)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE shadow_rows SET {sets} WHERE signal_id=? AND evaluated_at IS NULL",
                [_to_sql(v) for v in fields.values()] + [signal_id],
            )
            return cur.rowcount == 1

    def record_run(self, run_at: str, target_date: str, stats: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO evaluation_runs(run_at, target_date, stats_json) VALUES(?, ?, ?)",
                (run_at, target_date, json.dumps(stats, sort_keys=True, default=str)),
            )


def _to_sql(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (list, dict, tuple)):
        return json.dumps(v)
    return v


def open_store(data_dir: Path) -> ShadowStore:
    return ShadowStore(Path(data_dir) / DB_FILENAME)


def iter_columns() -> Iterable[str]:
    return iter(S.COLUMN_NAMES)
