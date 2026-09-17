"""
sr_shadow/evaluator.py — §8 COUNTERFACTUAL ENTRY MODEL (not an execution
simulation), as amended by A4, A5, A6 and addendum R8.

Strictly downstream of the decision: nothing here reads or writes a zone, stop,
target or decision field; it consumes them. The 5-minute candle is the ENTRY
EVENT only (ENTRY_EVENT_ONLY, R3): it never creates or alters structure.

Sources: broker 5-minute historical candles for the confirming candle (never
synthesised from 1-minute bars — addendum §4.3) and broker 1-minute candles for
the outcome scan.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from sr_shadow import params as P


def _naive(dt: datetime) -> datetime:
    """Drop tzinfo for wall-clock arithmetic. All timestamps are IST throughout
    (§5.8); aware values are IST already, so this never shifts a candle."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def confirming_candle_start(signal_ts: datetime) -> datetime:
    """§5.8: the first 5-minute candle whose START is >= the signal timestamp. A
    signal exactly on a 5-minute start selects that candle; a signal inside a
    candle selects the next one."""
    ts = _naive(signal_ts)
    floor = ts.replace(second=0, microsecond=0) - timedelta(minutes=ts.minute % P.CONFIRM_MINUTES)
    return floor if floor == ts else floor + timedelta(minutes=P.CONFIRM_MINUTES)


@dataclass(frozen=True)
class ConfirmInfo:
    status: str                      # CANDLE_OBTAINED | CANDLE_UNAVAILABLE
    start: datetime
    close_ts: datetime
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    no_eval_window: bool             # R8: confirming candle closes at/after 15:00


def select_confirming_candle(signal_ts: datetime, candles_5m: Sequence, fetched_at: datetime) -> ConfirmInfo:
    """Only a COMPLETED broker 5-minute candle whose start equals the computed
    start is accepted (A4). Never the previous candle, a partial candle, a
    1-minute candle, or a synthesised close."""
    start = confirming_candle_start(signal_ts)
    close_ts = start + timedelta(minutes=P.CONFIRM_MINUTES)
    no_eval_window = close_ts.time() >= P.EVAL_WINDOW_END or close_ts.date() != start.date()
    match = None
    for c in candles_5m:
        if _naive(c.ts) == start:
            match = c
            break
    completed = close_ts <= _naive(fetched_at)
    if match is None or not completed:
        return ConfirmInfo(P.CONFIRM_STATUS_UNAVAILABLE, start, close_ts, None, None, None, None, no_eval_window)
    return ConfirmInfo(
        P.CONFIRM_STATUS_OBTAINED, start, close_ts,
        float(match.open), float(match.high), float(match.low), float(match.close), no_eval_window,
    )


def counterfactual_entry_invalid(direction: str, stop: float, target: float,
                                 window_high: float, window_low: float, confirm_close: float) -> bool:
    """A6 — checked BEFORE any 1-minute bar is scanned, using the confirming
    candle's HIGH, LOW and CLOSE. Equality counts in every case."""
    if direction == P.LONG:
        return (window_low <= stop or window_high >= target
                or confirm_close <= stop or confirm_close >= target)
    return (window_high >= stop or window_low <= target
            or confirm_close >= stop or confirm_close <= target)


def reconciliation(direction: str, stop: float, target: float, confirm_close: float) -> Dict[str, Optional[float]]:
    """§8.3 SIGNED directional distances (short-side fields only for SHORT and
    vice versa) and the implied R:R at the confirming close."""
    out: Dict[str, Optional[float]] = {
        "target_minus_confirm_entry": None,
        "confirm_entry_minus_stop": None,
        "confirm_entry_minus_target": None,
        "stop_minus_confirm_entry": None,
        "confirm_entry_implied_rr": None,
    }
    if direction == P.LONG:
        t_side = target - confirm_close
        s_side = confirm_close - stop
        out["target_minus_confirm_entry"] = t_side
        out["confirm_entry_minus_stop"] = s_side
    else:
        t_side = confirm_close - target
        s_side = stop - confirm_close
        out["confirm_entry_minus_target"] = t_side
        out["stop_minus_confirm_entry"] = s_side
    out["confirm_entry_implied_rr"] = (t_side / s_side) if s_side > 0 else None
    return out


@dataclass(frozen=True)
class Resolution:
    outcome: str
    sub_reason: Optional[str]
    resolution_price: Optional[float]
    resolution_timestamp: Optional[datetime]
    gap_slippage_rupees: Optional[float]
    gap_slippage_atr: Optional[float]


def resolve_outcome(direction: str, stop: float, target: float, entry_event_close: datetime,
                    minute_bars: Sequence, atr14: Optional[float]) -> Resolution:
    """§8.4–8.8 with R8. Eligible bars begin at or after T (the confirming close)
    and before 15:00. Every minute in [T, 14:59] is required; the scan is
    chronological and STOPS at the first missing bar (DATA_UNAVAILABLE_OUTCOME_BARS)
    — it never skips a hole. TIME_CLOSE resolves at the close of the 14:59 bar."""
    t0 = _naive(entry_event_close)
    by_start: Dict[datetime, object] = {}
    for b in minute_bars:
        by_start[_naive(b.ts)] = b
    end_start = datetime.combine(t0.date(), P.TIME_CLOSE_BAR_START)
    cursor = t0
    last_bar = None
    while cursor <= end_start:
        bar = by_start.get(cursor)
        if bar is None:
            return Resolution(P.OUTCOME_DATA_UNAVAILABLE, P.DU_OUTCOME_BARS, None, None, None, None)
        o, h, l, c = float(bar.open), float(bar.high), float(bar.low), float(bar.close)
        if direction == P.LONG:
            stop_hit = l <= stop
            target_hit = h >= target
        else:
            stop_hit = h >= stop
            target_hit = l <= target
        if stop_hit and target_hit:
            return Resolution(P.OUTCOME_AMBIGUOUS_SAME_BAR, None, None, cursor, None, None)
        if stop_hit or target_hit:
            level = stop if stop_hit else target
            if direction == P.LONG:
                gapped = (o <= stop) if stop_hit else (o >= target)
            else:
                gapped = (o >= stop) if stop_hit else (o <= target)
            price = o if gapped else level
            slip = abs(o - level) if gapped else 0.0
            slip_atr = (slip / atr14) if (atr14 and atr14 > 0) else None
            return Resolution(P.OUTCOME_STOP_HIT if stop_hit else P.OUTCOME_TARGET_HIT,
                              None, price, cursor, slip, slip_atr)
        last_bar = bar
        cursor += timedelta(minutes=1)
    if last_bar is None:
        return Resolution(P.OUTCOME_DATA_UNAVAILABLE, P.DU_NO_EVAL_WINDOW, None, None, None, None)
    close_at = datetime.combine(t0.date(), P.EVAL_WINDOW_END)
    return Resolution(P.OUTCOME_TIME_CLOSE, None, float(last_bar.close), close_at, None, None)


def evaluate_signal(row: Dict[str, object], candles_5m: Sequence, minute_bars: Sequence,
                    fetched_at: datetime) -> Dict[str, object]:
    """Evaluate one decided row. Returns ONLY evaluator-owned fields (confirmation
    fields, §8.3 reconciliation and outcome fields for both variants). Decision
    fields are read, never written."""
    out: Dict[str, object] = {}
    signal_ts = datetime.fromisoformat(str(row["signal_timestamp_used"]))

    # A decision-level DATA_UNAVAILABLE row: no structural decision exists (§1.4).
    du = row.get("data_unavailable_sub_reason")
    confirm = select_confirming_candle(signal_ts, candles_5m, fetched_at)
    out["confirmation_status"] = confirm.status
    out["confirm_candle_start"] = confirm.start.isoformat()
    out["confirm_entry_price"] = confirm.close
    out["evaluator_entry_price"] = confirm.close
    out["confirm_window_high"] = confirm.high
    out["confirm_window_low"] = confirm.low
    out["confirm_window_range"] = (confirm.high - confirm.low) if confirm.status == P.CONFIRM_STATUS_OBTAINED else None

    for v in P.VARIANTS:
        pref = f"{v}_"
        decision = row.get(pref + "decision")
        stop = row.get(pref + "stop_v1")
        target = row.get(pref + "target")
        res: Dict[str, object] = {
            "outcome": None, "outcome_sub_reason": None, "resolution_price": None,
            "resolution_timestamp": None, "gap_slippage_rupees": None, "gap_slippage_atr": None,
        }
        if du:
            res["outcome"], res["outcome_sub_reason"] = P.OUTCOME_DATA_UNAVAILABLE, du
        elif decision == P.DECISION_INVARIANT_VIOLATION:
            res["outcome"] = P.OUTCOME_INVARIANT_VIOLATION
        elif stop is None or target is None:
            res["outcome"] = None  # no stop/target to evaluate (structure absent or unlocked)
        elif confirm.no_eval_window:
            res["outcome"], res["outcome_sub_reason"] = P.OUTCOME_DATA_UNAVAILABLE, P.DU_NO_EVAL_WINDOW
        elif confirm.status != P.CONFIRM_STATUS_OBTAINED:
            res["outcome"], res["outcome_sub_reason"] = P.OUTCOME_DATA_UNAVAILABLE, P.DU_NO_CONFIRM_CANDLE
        else:
            direction = str(row["direction"])
            stop_f, target_f = float(stop), float(target)
            for k, val in reconciliation(direction, stop_f, target_f, confirm.close).items():
                out[pref + k] = val
            if counterfactual_entry_invalid(direction, stop_f, target_f, confirm.high, confirm.low, confirm.close):
                res["outcome"] = P.OUTCOME_COUNTERFACTUAL_ENTRY_INVALID
            else:
                atr = row.get("atr14_rupees")
                r = resolve_outcome(direction, stop_f, target_f, confirm.close_ts, minute_bars,
                                    float(atr) if atr is not None else None)
                res["outcome"] = r.outcome
                res["outcome_sub_reason"] = r.sub_reason
                res["resolution_price"] = r.resolution_price
                res["resolution_timestamp"] = r.resolution_timestamp.isoformat() if r.resolution_timestamp else None
                res["gap_slippage_rupees"] = r.gap_slippage_rupees
                res["gap_slippage_atr"] = r.gap_slippage_atr
        for k, val in res.items():
            out[pref + k] = val
    return out


# ─────────────────────────────────────────────────────────────────────────────
# addendum §4.5 outcome statistics — never mixing DATA_UNAVAILABLE into the
# market-outcome denominator
# ─────────────────────────────────────────────────────────────────────────────


def outcome_statistics(rows: Iterable[Dict[str, object]]) -> Dict[str, object]:
    rows = list(rows)
    stats: Dict[str, object] = {
        "total_rows": len(rows),
        "rows_with_trustworthy_p": sum(1 for r in rows if r.get("p_provenance_available")),
        "rows_with_contract_formula_undefined_fields": sum(
            1 for r in rows if r.get("contract_formula_undefined_fields") not in (None, "", "[]")
        ),
        "invariant_violation_rows": sum(1 for r in rows if r.get("invariant_violation_flag")),
        "variants": {},
    }
    for v in P.VARIANTS:
        pref = f"{v}_"
        eligible = [r for r in rows if not r.get("invariant_violation_flag")]  # A7: excluded from all statistics
        bucket = _outcome_bucket(eligible, pref)
        decisions = sorted({str(r.get(pref + "decision")) for r in eligible if r.get(pref + "outcome") is not None})
        # Counterfactual outcomes of REJECTED variants are reported separately and never
        # mixed into SHADOW_TRADE's figures.
        bucket["by_decision"] = {
            d: _outcome_bucket([r for r in eligible if str(r.get(pref + "decision")) == d], pref) for d in decisions
        }
        stats["variants"][v] = bucket
    return stats


def _outcome_bucket(rows: List[Dict[str, object]], pref: str) -> Dict[str, object]:
    counts: Dict[str, int] = {}
    du_by_reason: Dict[str, int] = {}
    for r in rows:
        o = r.get(pref + "outcome")
        if o is None:
            continue
        counts[o] = counts.get(o, 0) + 1
        if o == P.OUTCOME_DATA_UNAVAILABLE:
            sub = str(r.get(pref + "outcome_sub_reason"))
            du_by_reason[sub] = du_by_reason.get(sub, 0) + 1
    target_hit = counts.get(P.OUTCOME_TARGET_HIT, 0)
    stop_hit = counts.get(P.OUTCOME_STOP_HIT, 0)
    time_close = counts.get(P.OUTCOME_TIME_CLOSE, 0)
    ambiguous = counts.get(P.OUTCOME_AMBIGUOUS_SAME_BAR, 0)
    resolvable = target_hit + stop_hit + time_close
    return {
        "data_unavailable_by_sub_reason": du_by_reason,
        "counterfactual_entry_invalid": counts.get(P.OUTCOME_COUNTERFACTUAL_ENTRY_INVALID, 0),
        "ambiguous_same_bar": ambiguous,
        "resolvable_outcomes": resolvable,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "time_close": time_close,
        # §8.6: a separate worst-case stress statistic counts AMBIGUOUS_SAME_BAR as STOP_HIT
        "stress_stop_hit_including_ambiguous": stop_hit + ambiguous,
        "stress_denominator_including_ambiguous": resolvable + ambiguous,
    }
