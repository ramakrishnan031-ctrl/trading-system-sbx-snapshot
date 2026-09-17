"""
sr_shadow/schema.py — the §9 log schema (with A2, A4, A5, A6 and addendum
additions) as the SINGLE source of truth for sr_shadow.db columns.

Every decision-dependent field carries a strict_ or recency_ prefix; there is no
unprefixed copy of any of them (§9, §10.13). No field is named "fill" (A5).
"""
from __future__ import annotations

from typing import List, Tuple

from sr_shadow import params as P

REAL, INTEGER, TEXT = "REAL", "INTEGER", "TEXT"

SHARED_COLUMNS: List[Tuple[str, str]] = [
    ("shadow_contract_version", TEXT),
    ("calibration_json", TEXT),
    ("date", TEXT),
    ("time_ist", TEXT),
    ("signal_timestamp_used", TEXT),
    ("signal_timestamp_source", TEXT),
    ("captured_at", TEXT),
    ("mode", TEXT),
    ("symbol", TEXT),
    ("scanner", TEXT),
    ("strategy", TEXT),
    ("direction", TEXT),
    ("chartink_trigger_price", REAL),
    ("structural_entry_price", REAL),
    ("confirm_entry_price", REAL),
    ("decision_reference_entry", REAL),
    ("evaluator_entry_price", REAL),
    ("p_provenance_available", INTEGER),
    ("tick_size", REAL),
    ("atr14_rupees", REAL),
    ("atr14_pct", REAL),
    ("daily_range_rupees", REAL),
    ("daily_range_pct", REAL),
    ("history_first_candle_date", TEXT),
    ("history_candle_count", INTEGER),
    ("history_span_days", INTEGER),
    ("history_weekday_coverage_pct", REAL),
    ("calendar_coverage_start", TEXT),
    ("history_meets_split_flag", INTEGER),
    ("session_gap_check_status", TEXT),
    ("session_gap_missing_dates", TEXT),
    ("confirmation_rule_bound", TEXT),
    ("confirmation_function_name", TEXT),
    ("confirmation_result", TEXT),
    ("confirmation_status", TEXT),
    ("confirm_candle_start", TEXT),
    ("confirm_window_high", REAL),
    ("confirm_window_low", REAL),
    ("confirm_window_range", REAL),
    ("trading_calendar_source", TEXT),
    ("data_unavailable_sub_reason", TEXT),
    ("decision_agreement_flag", INTEGER),
    ("shadow_decision", TEXT),
    ("invariant_violation_flag", INTEGER),
    ("admission_status", TEXT),
    ("admission_reason", TEXT),
    ("contract_formula_undefined_fields", TEXT),
    ("decided_at", TEXT),
    ("evaluated_at", TEXT),
]

_ZONE_FIELDS: List[Tuple[str, str]] = [
    ("lower_edge", REAL),
    ("upper_edge", REAL),
    ("near_edge", REAL),
    ("far_edge", REAL),
    ("pivot_count", INTEGER),
    ("touch_count", INTEGER),
    ("timeframes", TEXT),
    ("source_zone_ids", TEXT),
    ("source_timeframes", TEXT),
    ("source_zone_edges", TEXT),
    ("source_body_edges", TEXT),
    ("source_wick_edges", TEXT),
    ("source_origin_sides", TEXT),
    ("source_cluster_count", INTEGER),
    ("daily_member_count", INTEGER),
    ("weekly_member_count", INTEGER),
    ("final_zone_width_pct", REAL),
    ("merge_enlarged_flag", INTEGER),
    ("cross_timeframe_merge_flag", INTEGER),
    ("mixed_origin_flag", INTEGER),
    ("structure_uncertain_flag", INTEGER),
    ("flip_transitions", TEXT),
    ("flip_result_1close", TEXT),
    ("flip_result_2close", TEXT),
    ("zone_width_rupees", REAL),
    ("zone_width_pct", REAL),
    ("zone_width_div_atr", REAL),
    ("distance_entry_to_zone_div_atr", REAL),
    ("rejection_ratio", REAL),
    ("pivot_age_days", INTEGER),
    ("pivot_age_weeks", INTEGER),
]


def _variant_fields() -> List[Tuple[str, str]]:
    f: List[Tuple[str, str]] = [("chosen_support", TEXT), ("chosen_resistance", TEXT)]
    for side in ("support", "resistance"):
        f += [(f"{side}_{n}", t) for n, t in _ZONE_FIELDS]
    for side in ("support", "resistance"):
        for tf in ("1d", "1w"):
            f += [(f"nearest_source_{tf}_{side}", TEXT), (f"nearest_source_{tf}_{side}_near_edge", REAL)]
    f += [
        ("selection_difference_rupees_support", REAL),
        ("selection_difference_rupees_resistance", REAL),
        ("timeframe_changed_decision_flag", INTEGER),
        ("entry_inside_zone_flag", INTEGER),
        ("distance_to_nearest_edge_rupees", REAL),
        ("buffer_slab_source_price", REAL),
        ("buffer_reference_price", REAL),
        ("buffer_pct", REAL),
        ("buffer_rupees", REAL),
        ("buffer_variant_a_rupees", REAL),
        ("buffer_variant_b_rupees", REAL),
        ("buffer_variant_c_rupees", REAL),
        ("buffer_div_atr", REAL),
        ("distance_to_lower_boundary", REAL),
        ("distance_to_upper_boundary", REAL),
        ("boundary_within_2pct", INTEGER),
        ("adjacent_slab_buffer", REAL),
        ("slab_boundary_exact_flag", INTEGER),
        ("stop_v1", REAL),
    ]
    for n in (1, 2, 3):
        f += [
            (f"stop_candidate_l{n}_zone_id", TEXT),
            (f"stop_candidate_l{n}", REAL),
            (f"stop_candidate_l{n}_distance_rupees", REAL),
            (f"stop_candidate_l{n}_distance_pct", REAL),
            (f"stop_candidate_l{n}_distance_div_atr", REAL),
        ]
    f += [
        ("stop_distance_rupees", REAL),
        ("stop_distance_pct", REAL),
        ("stop_distance_div_atr", REAL),
        ("stop_distance_div_daily_range", REAL),
        ("stop_distance_band", TEXT),
        ("strategy_rr", REAL),
        ("risk_rupees", REAL),
        ("risk_pct", REAL),
        ("target", REAL),
        ("target_distance_rupees", REAL),
        ("target_distance_pct", REAL),
        ("target_div_atr", REAL),
        ("target_div_daily_range", REAL),
        ("structural_risk", REAL),
        ("target_minus_confirm_entry", REAL),
        ("confirm_entry_minus_stop", REAL),
        ("confirm_entry_minus_target", REAL),
        ("stop_minus_confirm_entry", REAL),
        ("confirm_entry_implied_rr", REAL),
        ("box_position_pct", REAL),
        ("rr_position_limit", REAL),
        ("position_test_pass", INTEGER),
        ("decision", TEXT),
        ("reject_code", TEXT),
        ("diagnostic_flags", TEXT),
        ("invariant_violation_detail", TEXT),
        ("outcome", TEXT),
        ("outcome_sub_reason", TEXT),
        ("resolution_price", REAL),
        ("resolution_timestamp", TEXT),
        ("gap_slippage_rupees", REAL),
        ("gap_slippage_atr", REAL),
    ]
    return f


VARIANT_FIELDS: List[Tuple[str, str]] = _variant_fields()

RECENCY_ONLY_COLUMNS: List[Tuple[str, str]] = [
    ("recency_support_recency_source_zone_id", TEXT),
    ("recency_resistance_recency_source_zone_id", TEXT),
]


def all_columns() -> List[Tuple[str, str]]:
    cols = list(SHARED_COLUMNS)
    for v in P.VARIANTS:
        cols += [(f"{v}_{n}", t) for n, t in VARIANT_FIELDS]
    cols += RECENCY_ONLY_COLUMNS
    return cols


COLUMN_NAMES: Tuple[str, ...] = tuple(n for n, _ in all_columns())
COLUMN_TYPES = dict(all_columns())

STATIC_UNDEFINED_SHARED_FIELDS = ("atr14_pct",)

# Columns the EOD evaluator may write (everything else is written once, at decision time).
_VARIANT_EVAL_FIELDS = (
    "target_minus_confirm_entry",
    "confirm_entry_minus_stop",
    "confirm_entry_minus_target",
    "stop_minus_confirm_entry",
    "confirm_entry_implied_rr",
    "outcome",
    "outcome_sub_reason",
    "resolution_price",
    "resolution_timestamp",
    "gap_slippage_rupees",
    "gap_slippage_atr",
)
EVALUATOR_COLUMNS: Tuple[str, ...] = (
    "confirmation_status",
    "confirm_candle_start",
    "confirm_entry_price",
    "evaluator_entry_price",
    "confirm_window_high",
    "confirm_window_low",
    "confirm_window_range",
    "admission_status",
    "admission_reason",
    "evaluated_at",
) + tuple(f"{v}_{n}" for v in P.VARIANTS for n in _VARIANT_EVAL_FIELDS)
