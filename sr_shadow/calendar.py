"""
sr_shadow/calendar.py — the project's authoritative trading calendar, adapted.

v1.2 §1.4 forbids writing a calendar inside the S&R module and forbids assuming
every weekday is a session. This adapter does neither:
  * session semantics are core.market_windows.MarketWindows.is_trading_holiday
    (weekend / configured NSE holiday / FIX-094 special session);
  * holidays come from EVERY config/nse_holidays_<year>.yaml present (validated by
    core.config_loader.NseHolidaysConfig), so adding a year's Capital-Market list
    later extends coverage with no code change (addendum §1);
  * a date in a year with no holiday file is NOT adjudicated: is_expected_session
    returns None and the caller never treats it as an expected session.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

_HOLIDAY_FILE_RE = re.compile(r"^nse_holidays_(\d{4})\.yaml$")
_MAX_WALKBACK_DAYS = 120  # bound for enumerating the last N expected sessions


class TradingCalendar:
    def __init__(
        self,
        holidays_by_year: Dict[int, Set[date]],
        special_sessions: Optional[Dict[date, Tuple[time, time, time]]] = None,
        source: str = "",
    ) -> None:
        from core.market_windows import MarketWindows

        self._years: Set[int] = set(holidays_by_year)
        all_holidays: Set[date] = set()
        for ds in holidays_by_year.values():
            all_holidays |= set(ds)
        self._mw = MarketWindows(holidays=all_holidays, special_sessions=dict(special_sessions or {}))
        self._source = source or "core.market_windows.MarketWindows + nse_holidays_<year>.yaml"

    # ── construction ────────────────────────────────────────────────────────
    @classmethod
    def from_config_dir(
        cls,
        config_dir: Path,
        special_sessions: Optional[Dict[date, Tuple[time, time, time]]] = None,
    ) -> "TradingCalendar":
        import yaml
        from core.config_loader import NseHolidaysConfig

        by_year: Dict[int, Set[date]] = {}
        files: List[str] = []
        for p in sorted(Path(config_dir).glob("nse_holidays_*.yaml")):
            m = _HOLIDAY_FILE_RE.match(p.name)
            if not m:
                continue
            year = int(m.group(1))
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            parsed = NseHolidaysConfig.model_validate(data)
            by_year[year] = {h.date for h in parsed.holidays}
            files.append(p.name)
        source = (
            "core.market_windows.MarketWindows.is_trading_holiday over "
            + (", ".join(files) if files else "NO nse_holidays_<year>.yaml FILE")
        )
        return cls(by_year, special_sessions=special_sessions, source=source)

    # ── queries ─────────────────────────────────────────────────────────────
    @property
    def source(self) -> str:
        return self._source

    @property
    def covered_years(self) -> Tuple[int, ...]:
        return tuple(sorted(self._years))

    def is_expected_session(self, d: date) -> Optional[bool]:
        """True/False when the calendar can adjudicate `d`; None when it cannot."""
        if d.year not in self._years:
            return None
        return not self._mw.is_trading_holiday(datetime.combine(d, time(12, 0)))

    def coverage_start(self, decision_date: date) -> Optional[date]:
        """First date of the contiguous run of covered years ending at the decision
        year — the first date from which the calendar can adjudicate every date up
        to the decision. None when the decision year itself is uncovered."""
        year = decision_date.year
        if year not in self._years:
            return None
        while (year - 1) in self._years:
            year -= 1
        return date(year, 1, 1)

    def last_expected_sessions(self, before: date, n: int) -> Optional[List[date]]:
        """The n most recent expected sessions strictly before `before`, newest
        first; None when enumerating them would need a date the calendar cannot
        adjudicate."""
        out: List[date] = []
        d = before - timedelta(days=1)
        for _ in range(_MAX_WALKBACK_DAYS):
            expected = self.is_expected_session(d)
            if expected is None:
                return None
            if expected:
                out.append(d)
                if len(out) == n:
                    return out
            d -= timedelta(days=1)
        return None


def weekdays_in_span(first: date, last: date) -> int:
    """Count Monday-Friday dates in the inclusive span [first, last]."""
    if last < first:
        return 0
    total = (last - first).days + 1
    full_weeks, rem = divmod(total, 7)
    count = full_weeks * 5
    wd = first.weekday()
    for i in range(rem):
        if (wd + i) % 7 < 5:
            count += 1
    return count


def iter_dates(first: date, last: date) -> Iterable[date]:
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)
