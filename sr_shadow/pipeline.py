"""
sr_shadow/pipeline.py — assemble ONE decision row from an immutable screener-pass
snapshot and the raw daily candle history. Pure: no I/O, no clock, no broker.

The map is rebuilt from scratch for every call (§0.6). Both validity variants are
built from the same structure map and decided independently; neither mutates the
other's state (addendum §4.7). structural_entry_price comes ONLY from the snapshot
— it is never re-derived here (addendum §2.1).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence

from core.daily_stats import compute_daily_stats
from sr_shadow import params as P
from sr_shadow import schema as S
from sr_shadow.bars import (
    build_weekly,
    check_data_available,
    completed_daily,
    history_coverage,
)
from sr_shadow.calendar import TradingCalendar
from sr_shadow.decision import decide_variant, distance_to_nearest_edge, observe_variant
from sr_shadow.zones import build_structure_map, valid_recency, valid_strict


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat()


def compute_decision_row(
    snapshot: Dict[str, object],
    signal_timestamp: datetime,
    raw_daily: Sequence,
    calendar: TradingCalendar,
    calibration: P.Calibration,
    tick_size: float,
    decided_at: str,
    on_invariant_violation: Optional[Callable[[dict], None]] = None,
) -> Dict[str, object]:
    entry = float(snapshot["structural_entry_price"])
    direction = str(snapshot["direction"])
    strategy_rr = float(snapshot["strategy_rr"])
    decision_date: date = signal_timestamp.date()

    daily = completed_daily(raw_daily, decision_date)
    weekly = build_weekly(daily, decision_date)
    atr14 = compute_daily_stats(daily, decision_date.isoformat(), atr_period=P.ATR_PERIOD)["atr14"]
    coverage = history_coverage(daily, decision_date, calendar,
                                calibration.history_coverage_diagnostic_split_years)
    availability = check_data_available(daily, decision_date, calendar, atr14)
    daily_range = (float(daily[-1].high) - float(daily[-1].low)) if daily else None

    undefined: List[str] = list(S.STATIC_UNDEFINED_SHARED_FIELDS)
    row: Dict[str, object] = {
        "shadow_contract_version": P.CONTRACT_VERSION,
        "calibration_json": calibration.as_json(),
        "date": decision_date.isoformat(),
        "time_ist": signal_timestamp.time().isoformat(),
        "signal_timestamp_used": signal_timestamp.isoformat(),
        "signal_timestamp_source": P.SIGNAL_TIMESTAMP_SOURCE,
        "captured_at": snapshot.get("captured_at"),
        "mode": snapshot.get("mode"),
        "symbol": snapshot["symbol"],
        "scanner": snapshot.get("scanner"),
        "strategy": snapshot.get("strategy"),
        "direction": direction,
        "chartink_trigger_price": snapshot.get("chartink_trigger_price"),
        "structural_entry_price": entry,
        "decision_reference_entry": entry,
        "p_provenance_available": False,  # A2 reading A: false on every row of this build
        "tick_size": tick_size,
        "atr14_rupees": atr14,
        "atr14_pct": None,
        "daily_range_rupees": daily_range,
        "daily_range_pct": (daily_range / entry * 100.0) if daily_range is not None else None,
        "history_first_candle_date": _iso(coverage.history_first_candle_date),
        "history_candle_count": coverage.history_candle_count,
        "history_span_days": coverage.history_span_days,
        "history_weekday_coverage_pct": coverage.history_weekday_coverage_pct,
        "calendar_coverage_start": _iso(coverage.calendar_coverage_start),
        "history_meets_split_flag": coverage.history_meets_split_flag,
        "session_gap_check_status": availability.session_gap_check_status,
        "session_gap_missing_dates": availability.missing_dates_json,
        "confirmation_rule_bound": P.CONFIRMATION_RULE_BOUND,
        "confirmation_function_name": None,
        "confirmation_result": None,
        "trading_calendar_source": calendar.source,
        "data_unavailable_sub_reason": availability.sub_reason,
        "decided_at": decided_at,
    }

    if availability.sub_reason is not None:
        # §1.4: record NO structural decision.
        for v in P.VARIANTS:
            row[f"{v}_decision"] = P.DECISION_DATA_UNAVAILABLE
            for name in _static_undefined_variant():
                undefined.append(f"{v}_{name}")
        row["decision_agreement_flag"] = True
        row["shadow_decision"] = P.DECISION_DATA_UNAVAILABLE
        row["invariant_violation_flag"] = False
        row["contract_formula_undefined_fields"] = json.dumps(sorted(set(undefined)))
        return row

    smap = build_structure_map(daily, weekly, calibration)
    strict_validity = {z.final_id: valid_strict(z) for z in smap.final_zones}
    recency_eval = {z.final_id: valid_recency(z, smap.latest_ids, calibration.rejection_ratio_min)
                    for z in smap.final_zones}
    recency_validity = {k: v[0] for k, v in recency_eval.items()}
    history_meets_split = coverage.history_meets_split_flag

    results = {}
    for variant, validity in ((P.VARIANT_STRICT, strict_validity), (P.VARIANT_RECENCY, recency_validity)):
        vr = decide_variant(
            variant, smap.final_zones, validity, entry, direction, strategy_rr, tick_size,
            calibration.slabs, history_meets_split, on_invariant_violation=on_invariant_violation,
        )
        obs = observe_variant(vr, entry, direction, strategy_rr, tick_size, calibration.slabs,
                              float(atr14), daily_range, decision_date)
        valid_zones = [z for z in smap.final_zones if validity.get(z.final_id)]
        obs["distance_to_nearest_edge_rupees"] = distance_to_nearest_edge(valid_zones, entry)
        for name in obs.pop("__undefined__"):
            undefined.append(f"{variant}_{name}")
        for k, val in obs.items():
            row[f"{variant}_{k}"] = val
        results[variant] = vr

    for side_name, zone in (("support", results[P.VARIANT_RECENCY].support),
                            ("resistance", results[P.VARIANT_RECENCY].resistance)):
        row[f"recency_{side_name}_recency_source_zone_id"] = (
            recency_eval[zone.final_id][1] if zone is not None else None
        )

    d_strict = results[P.VARIANT_STRICT].decision
    d_recency = results[P.VARIANT_RECENCY].decision
    invariant = P.DECISION_INVARIANT_VIOLATION in (d_strict, d_recency)
    row["decision_agreement_flag"] = d_strict == d_recency
    if invariant:
        row["shadow_decision"] = P.DECISION_INVARIANT_VIOLATION
    elif d_strict == d_recency:
        row["shadow_decision"] = d_strict
    else:
        row["shadow_decision"] = P.SHADOW_DECISION_AMBIGUOUS
    row["invariant_violation_flag"] = invariant
    row["contract_formula_undefined_fields"] = json.dumps(sorted(set(undefined)))
    return row


def _static_undefined_variant():
    from sr_shadow.decision import STATIC_UNDEFINED_VARIANT_FIELDS
    return STATIC_UNDEFINED_VARIANT_FIELDS
