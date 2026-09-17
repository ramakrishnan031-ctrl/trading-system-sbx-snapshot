"""
sr_shadow/bars.py — completed daily / weekly candles, history coverage, and the
DATA_UNAVAILABLE checks (v1.2 §1.1, §1.4 as scoped by the addendum §1).

Candles are duck-typed on the shared sr_detector.models.Candle (ts, open, high,
low, close, volume). No lookahead: only daily candles dated STRICTLY BEFORE the
decision date are ever returned; the current (incomplete) week never becomes a
weekly candle.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence

from sr_shadow import params as P
from sr_shadow.calendar import TradingCalendar, weekdays_in_span


def bar_date(c) -> date:
    ts = c.ts
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, date):
        return ts
    return date.fromisoformat(str(ts)[:10])


def completed_daily(candles: Sequence, decision_date: date) -> list:
    """Completed daily candles strictly before `decision_date`, chronological.
    Today's candle is always excluded (§1.1). A duplicated date keeps the last
    occurrence in input order."""
    by_date = {}
    for c in candles:
        d = bar_date(c)
        if d < decision_date:
            by_date[d] = c
    return [by_date[d] for d in sorted(by_date)]


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_weekly(daily: Sequence, decision_date: date) -> list:
    """Completed Monday–Sunday weekly candles built from completed daily candles
    (§1.4). The week containing `decision_date` is the current incomplete week and
    is excluded. A week with zero sessions produces no candle. The weekly candle's
    date is the LAST ACTUAL trading session in that week (R7)."""
    from sr_detector.models import Candle  # the shared candle type (local import)

    current_week = monday_of(decision_date)
    groups: dict = {}
    for c in daily:
        wk = monday_of(bar_date(c))
        if wk >= current_week:
            continue
        groups.setdefault(wk, []).append(c)
    out = []
    for wk in sorted(groups):
        members = sorted(groups[wk], key=bar_date)
        last = members[-1]
        out.append(
            Candle(
                ts=last.ts,
                open=float(members[0].open),
                high=max(float(m.high) for m in members),
                low=min(float(m.low) for m in members),
                close=float(last.close),
                volume=int(sum(int(m.volume or 0) for m in members)),
            )
        )
    return out


@dataclass(frozen=True)
class HistoryCoverage:
    """Addendum §1 deeper-history coverage fields (logged, never voiding)."""
    history_first_candle_date: Optional[date]
    history_last_candle_date: Optional[date]
    history_candle_count: int
    history_span_days: Optional[int]
    history_weekday_coverage_pct: Optional[float]
    calendar_coverage_start: Optional[date]
    history_meets_split_flag: bool


def years_before(d: date, years: int) -> date:
    """Calendar anniversary `years` before `d` (29-Feb maps to 28-Feb)."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def history_coverage(
    daily: Sequence, decision_date: date, calendar: TradingCalendar, split_years: int
) -> HistoryCoverage:
    if not daily:
        return HistoryCoverage(None, None, 0, None, None, calendar.coverage_start(decision_date), False)
    first = bar_date(daily[0])
    last = bar_date(daily[-1])
    span_days = (last - first).days + 1
    weekdays = weekdays_in_span(first, last)
    coverage_pct = (len(daily) / weekdays * 100.0) if weekdays > 0 else None
    # R9/S9: calendar anniversary, not 3 × 365 — a DIAGNOSTIC split only.
    meets_split = first <= years_before(decision_date, split_years)
    return HistoryCoverage(
        history_first_candle_date=first,
        history_last_candle_date=last,
        history_candle_count=len(daily),
        history_span_days=span_days,
        history_weekday_coverage_pct=coverage_pct,
        calendar_coverage_start=calendar.coverage_start(decision_date),
        history_meets_split_flag=meets_split,
    )


@dataclass(frozen=True)
class DataAvailability:
    sub_reason: Optional[str]
    session_gap_check_status: str
    session_gap_missing_dates: List[date]

    @property
    def missing_dates_json(self) -> str:
        return json.dumps([d.isoformat() for d in self.session_gap_missing_dates])


def check_data_available(
    daily: Sequence, decision_date: date, calendar: TradingCalendar, atr14: Optional[float]
) -> DataAvailability:
    """v1.2 §1.4 DATA_UNAVAILABLE, with the addendum §1 scoping of the session-gap
    check to the completeness-critical window (the last 15 completed sessions)."""
    gap_status = P.GAP_CHECK_UNADJUDICABLE
    missing: List[date] = []
    expected = calendar.last_expected_sessions(decision_date, P.SESSION_GAP_WINDOW)
    if expected is not None:
        gap_status = P.GAP_CHECK_CHECKED
        present = {bar_date(c) for c in daily}
        missing = sorted(d for d in expected if d not in present)

    if len(daily) < P.MIN_COMPLETED_DAILY:
        return DataAvailability(P.DU_HISTORY, gap_status, missing)
    if (decision_date - bar_date(daily[-1])).days > P.MAX_LAST_DAILY_AGE_DAYS:
        return DataAvailability(P.DU_HISTORY, gap_status, missing)
    if missing:
        return DataAvailability(P.DU_SESSION_GAP, gap_status, missing)
    if atr14 is None or atr14 <= 0:
        return DataAvailability(P.DU_ATR, gap_status, missing)
    return DataAvailability(None, gap_status, missing)
