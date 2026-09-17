"""
sr_shadow/decision.py — the §5 decision path (A8 order), run once per validity
variant, plus the §7 observations for that variant.

THE VALIDATOR MUST NOT SEARCH FOR STRUCTURE THAT MAKES A TRADE PASS (§0.5): the
nearest legitimate zone is locked and never re-selected; the stop is never moved;
the target is never widened; a farther wall is never substituted.

`decide_variant` is the §5 path and has NO ATR input (§7.2: zero ATR terms in the
decision path). ATR enters only `observe_variant`, which never feeds back.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence

from sr_shadow import params as P
from sr_shadow.pricing import (
    StopCalc,
    adjacent_slab_pct,
    compute_stop,
    dec,
    pick_slab,
    stop_invariant_holds,
)
from sr_shadow.zones import FinalZone, PrelimZone


@dataclass
class VariantResult:
    variant: str
    decision: str
    reject_code: Optional[str]
    diagnostic_flags: List[str]
    valid_zone_ids: List[str]
    entry_inside_zone_flag: bool
    support: Optional[FinalZone]
    resistance: Optional[FinalZone]
    support_candidates: List[FinalZone]
    resistance_candidates: List[FinalZone]
    stop_calc: Optional[StopCalc]
    risk: Optional[float]
    target: Optional[float]
    invariant_violated: bool
    invariant_detail: Optional[dict]
    recency_source_ids: Dict[str, Optional[str]] = field(default_factory=dict)


def decide_variant(
    variant: str,
    final_zones: Sequence[FinalZone],
    validity: Dict[str, bool],
    entry: float,
    direction: str,
    strategy_rr: float,
    tick_size: float,
    slabs: Sequence[P.Slab],
    history_meets_split: bool,
    on_invariant_violation: Optional[Callable[[dict], None]] = None,
) -> VariantResult:
    """§5.3 → §5.10 for one variant. The reject code is the FIRST failing step in
    path order; every other failing condition is a diagnostic flag."""
    valid = [z for z in final_zones if validity.get(z.final_id, False)]
    failures: List[str] = []

    def fail(code: str) -> None:
        if code not in failures:
            failures.append(code)

    # 5.3 ENTRY_ZONE_CHECK (A8) — any valid FINAL zone containing the entry, inclusive.
    inside = [z for z in valid if z.lower_edge <= entry <= z.upper_edge]
    if inside:
        fail(P.REJECT_ENTRY_INSIDE_ZONE)

    # 5.4 REQUIRED_STRUCTURE_CHECK (A8) — both sides required for LONG and SHORT.
    support_cands = sorted(
        (z for z in valid if z.side == P.SIDE_SUPPORT and z.upper_edge < entry),
        key=lambda z: (entry - z.upper_edge, z.final_id),
    )
    resistance_cands = sorted(
        (z for z in valid if z.side == P.SIDE_RESISTANCE and z.lower_edge > entry),
        key=lambda z: (z.lower_edge - entry, z.final_id),
    )
    support_clean = [z for z in support_cands if not z.structure_uncertain_flag]
    resistance_clean = [z for z in resistance_cands if not z.structure_uncertain_flag]
    # §3.5: an absence CAUSED by excluding conflicting zones is STRUCTURE_UNCERTAIN.
    if (support_cands and not support_clean) or (resistance_cands and not resistance_clean):
        fail(P.REJECT_STRUCTURE_UNCERTAIN)
    if not support_cands or not resistance_cands:
        fail(P.REJECT_ABSENT_CLEAR_AIR if history_meets_split else P.REJECT_ABSENT_HISTORY_LTD)

    # 5.5 LOCK_NEAREST_S_R — nearest by price to the NEAR edge (§4.2); never re-selected.
    support = support_cands[0] if support_cands else None
    resistance = resistance_cands[0] if resistance_cands else None
    if (support is not None and support.structure_uncertain_flag) or (
        resistance is not None and resistance.structure_uncertain_flag
    ):
        fail(P.REJECT_STRUCTURE_UNCERTAIN)

    # 5.6 STOP invariant (A7) — an assertion, not a decision step.
    stop_zone = support if direction == P.LONG else resistance
    target_zone = resistance if direction == P.LONG else support
    stop_calc: Optional[StopCalc] = None
    invariant_violated = False
    invariant_detail: Optional[dict] = None
    if stop_zone is not None:
        far_edge = stop_zone.lower_edge if direction == P.LONG else stop_zone.upper_edge
        stop_calc = compute_stop(direction, far_edge, entry, tick_size, slabs)
        if not stop_invariant_holds(direction, stop_calc.stop, far_edge):
            invariant_violated = True
            invariant_detail = {
                "variant": variant,
                "direction": direction,
                "structural_entry_price": entry,
                "stop_zone_id": stop_zone.final_id,
                "far_edge": far_edge,
                "buffer_slab_source_price": stop_calc.buffer_slab_source_price,
                "buffer_reference_price": stop_calc.buffer_reference_price,
                "buffer_pct": str(stop_calc.buffer_pct),
                "buffer_rupees": str(stop_calc.buffer_rupees),
                "candidate_stop": str(stop_calc.candidate_stop),
                "stop": str(stop_calc.stop),
                "tick_size": tick_size,
            }
            if on_invariant_violation is not None:
                on_invariant_violation(invariant_detail)

    # 5.7 TARGET_REACHABILITY_CHECK — against the opposing zone's NEAR edge.
    risk: Optional[float] = None
    target: Optional[float] = None
    if stop_calc is not None and not invariant_violated:
        stop = float(stop_calc.stop)
        risk = (entry - stop) if direction == P.LONG else (stop - entry)
        target = (entry + strategy_rr * risk) if direction == P.LONG else (entry - strategy_rr * risk)
        if target_zone is not None:
            if direction == P.LONG:
                reachable = target <= target_zone.lower_edge
            else:
                reachable = target >= target_zone.upper_edge
            if not reachable:
                fail(P.REJECT_TARGET_BEYOND_WALL)

    # 5.8 5M_CONFIRMATION — ENTRY_EVENT_ONLY (R3): CONFIRMATION_FAILED is never emitted.
    # 5.9 / 5.10 decision and reject code for this variant.
    if invariant_violated:
        decision, reject_code, diagnostics = P.DECISION_INVARIANT_VIOLATION, None, list(failures)
    elif failures:
        decision, reject_code, diagnostics = P.DECISION_REJECTED, failures[0], failures[1:]
    else:
        decision, reject_code, diagnostics = P.DECISION_SHADOW_TRADE, None, []

    return VariantResult(
        variant=variant, decision=decision, reject_code=reject_code,
        diagnostic_flags=diagnostics, valid_zone_ids=[z.final_id for z in valid],
        entry_inside_zone_flag=bool(inside), support=support, resistance=resistance,
        support_candidates=support_cands, resistance_candidates=resistance_cands,
        stop_calc=stop_calc, risk=risk, target=target,
        invariant_violated=invariant_violated, invariant_detail=invariant_detail,
    )


# ─────────────────────────────────────────────────────────────────────────────
# §7 observations — computed, logged, never deciding
# ─────────────────────────────────────────────────────────────────────────────

# Fields named in v1.2 §7.4/§9 for which neither v1.2 nor the addendum gives a
# formula (addendum §3: NULL + CONTRACT_FORMULA_UNDEFINED, never inferred).
STATIC_UNDEFINED_VARIANT_FIELDS = (
    "support_final_zone_width_pct",
    "support_merge_enlarged_flag",
    "support_zone_width_pct",
    "support_rejection_ratio",
    "resistance_final_zone_width_pct",
    "resistance_merge_enlarged_flag",
    "resistance_zone_width_pct",
    "resistance_rejection_ratio",
    "stop_candidate_l1_distance_pct",
    "stop_candidate_l2_distance_pct",
    "stop_candidate_l3_distance_pct",
    "stop_distance_pct",
    "risk_pct",
    "target_distance_pct",
)


def stop_distance_band(ratio: Optional[float]) -> Optional[str]:
    """Addendum §3 bands (ATR units): [0,0.5) · [0.5,0.75) · [0.75,1.0) · [1.0,1.25) ·
    [1.25,1.5] · (1.5,∞) — the literal "<0.5" and ">1.5" ends are honoured."""
    if ratio is None:
        return None
    e = P.STOP_DISTANCE_BAND_EDGES
    labels = P.STOP_DISTANCE_BAND_LABELS
    if ratio < e[0]:
        return labels[0]
    if ratio < e[1]:
        return labels[1]
    if ratio < e[2]:
        return labels[2]
    if ratio < e[3]:
        return labels[3]
    if ratio <= e[4]:
        return labels[4]
    return labels[5]


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _nearest_source(candidates: Sequence[FinalZone], side: str, timeframe: str,
                    entry: float) -> Optional[PrelimZone]:
    """The nearest `timeframe`-sourced preliminary zone among the sources of the
    valid candidate final zones on `side`, by distance to its own near edge."""
    best: Optional[PrelimZone] = None
    best_dist: Optional[float] = None
    for fz in candidates:
        for src in fz.sources:
            if src.timeframe != timeframe:
                continue
            near = src.upper_edge if side == P.SIDE_SUPPORT else src.lower_edge
            dist = abs(entry - near)
            if best_dist is None or dist < best_dist or (dist == best_dist and src.zone_id < best.zone_id):
                best, best_dist = src, dist
    return best


def _single_timeframe_decision(timeframe: str, vr: VariantResult, entry: float, direction: str,
                               strategy_rr: float, tick_size: float,
                               slabs: Sequence[P.Slab]) -> str:
    """Addendum §3 timeframe_changed_decision_flag: the §5 decision using the
    nearest `timeframe`-sourced zone alone on each side."""
    s = _nearest_source(vr.support_candidates, P.SIDE_SUPPORT, timeframe, entry)
    r = _nearest_source(vr.resistance_candidates, P.SIDE_RESISTANCE, timeframe, entry)
    if s is None or r is None:
        return P.DECISION_REJECTED
    far = s.lower_edge if direction == P.LONG else r.upper_edge
    sc = compute_stop(direction, far, entry, tick_size, slabs)
    if not stop_invariant_holds(direction, sc.stop, far):
        return P.DECISION_INVARIANT_VIOLATION
    stop = float(sc.stop)
    if direction == P.LONG:
        target = entry + strategy_rr * (entry - stop)
        return P.DECISION_SHADOW_TRADE if target <= r.lower_edge else P.DECISION_REJECTED
    target = entry - strategy_rr * (stop - entry)
    return P.DECISION_SHADOW_TRADE if target >= s.upper_edge else P.DECISION_REJECTED


def _zone_fields(zone: Optional[FinalZone], entry: float, atr14: float,
                 decision_date: date) -> Dict[str, object]:
    if zone is None:
        return {}
    near, far = zone.near_far(entry)
    width = zone.upper_edge - zone.lower_edge
    pivot_age_days = (decision_date - zone.latest_member_date).days
    return {
        "lower_edge": zone.lower_edge,
        "upper_edge": zone.upper_edge,
        "near_edge": near,
        "far_edge": far,
        "pivot_count": zone.pivot_count,
        "touch_count": zone.touch_count,
        "timeframes": json.dumps(list(zone.timeframes)),
        "source_zone_ids": json.dumps([s.zone_id for s in zone.sources]),
        "source_timeframes": json.dumps(list(zone.source_timeframes)),
        "source_zone_edges": json.dumps([[s.lower_edge, s.upper_edge] for s in zone.sources]),
        "source_body_edges": json.dumps([s.source_body_edge for s in zone.sources]),
        "source_wick_edges": json.dumps([s.source_wick_edge for s in zone.sources]),
        "source_origin_sides": json.dumps([s.origin_side for s in zone.sources]),
        "source_cluster_count": len(zone.sources),
        "daily_member_count": zone.daily_member_count,
        "weekly_member_count": zone.weekly_member_count,
        "cross_timeframe_merge_flag": zone.cross_timeframe_merge_flag,
        "mixed_origin_flag": zone.mixed_origin_flag,
        "structure_uncertain_flag": zone.structure_uncertain_flag,
        "flip_transitions": zone.flip_transitions_json(),
        "flip_result_1close": zone.flip_result_1close(),
        "flip_result_2close": zone.flip_result_2close(),
        "zone_width_rupees": width,
        "zone_width_div_atr": _div(width, atr14),
        "distance_entry_to_zone_div_atr": _div(abs(entry - near), atr14) if near is not None else None,
        "pivot_age_days": pivot_age_days,
        "pivot_age_weeks": pivot_age_days // 7,
    }


def observe_variant(
    vr: VariantResult,
    entry: float,
    direction: str,
    strategy_rr: float,
    tick_size: float,
    slabs: Sequence[P.Slab],
    atr14: float,
    daily_range: Optional[float],
    decision_date: date,
) -> Dict[str, object]:
    """Every §7 observation for one variant, keyed WITHOUT the variant prefix.
    Returns the fields plus `__undefined__` (a list of field names that are NULL
    because no formula is defined)."""
    out: Dict[str, object] = {}
    undefined: List[str] = list(STATIC_UNDEFINED_VARIANT_FIELDS)

    out["chosen_support"] = vr.support.final_id if vr.support else None
    out["chosen_resistance"] = vr.resistance.final_id if vr.resistance else None
    for side_name, zone in (("support", vr.support), ("resistance", vr.resistance)):
        for k, v in _zone_fields(zone, entry, atr14, decision_date).items():
            out[f"{side_name}_{k}"] = v
        if zone is not None and zone.flip_result_2close() is None:
            undefined.append(f"{side_name}_flip_result_2close")

    # nearest-source 1D / 1W logging + selection difference (addendum §3)
    for side_const, side_name, cands in (
        (P.SIDE_SUPPORT, "support", vr.support_candidates),
        (P.SIDE_RESISTANCE, "resistance", vr.resistance_candidates),
    ):
        near_edges = {}
        for tf, tf_name in ((P.TF_DAILY, "1d"), (P.TF_WEEKLY, "1w")):
            src = _nearest_source(cands, side_const, tf, entry)
            out[f"nearest_source_{tf_name}_{side_name}"] = src.zone_id if src else None
            edge = None
            if src is not None:
                edge = src.upper_edge if side_const == P.SIDE_SUPPORT else src.lower_edge
            out[f"nearest_source_{tf_name}_{side_name}_near_edge"] = edge
            near_edges[tf] = edge
        if near_edges[P.TF_DAILY] is not None and near_edges[P.TF_WEEKLY] is not None:
            out[f"selection_difference_rupees_{side_name}"] = abs(near_edges[P.TF_DAILY] - near_edges[P.TF_WEEKLY])
        else:
            out[f"selection_difference_rupees_{side_name}"] = None
    out["timeframe_changed_decision_flag"] = (
        _single_timeframe_decision(P.TF_DAILY, vr, entry, direction, strategy_rr, tick_size, slabs)
        != _single_timeframe_decision(P.TF_WEEKLY, vr, entry, direction, strategy_rr, tick_size, slabs)
    )

    # entry fit
    out["entry_inside_zone_flag"] = vr.entry_inside_zone_flag
    # addendum §3: min over ALL valid final zones of |P − that zone's nearest edge|
    # (computed by the caller from the variant's valid zones; see pipeline)

    # buffer (§6.4, §7.2) and slab-boundary diagnostics (§6.5, addendum §3)
    slab = pick_slab(entry, slabs)
    p = dec(entry)
    d_lower = float(p - slab.lower) if slab.lower is not None else None
    d_upper = float(slab.upper - p) if slab.upper is not None else None
    out["distance_to_lower_boundary"] = d_lower
    out["distance_to_upper_boundary"] = d_upper
    limit = entry * P.BOUNDARY_WITHIN_PCT / 100.0
    out["boundary_within_2pct"] = any(d is not None and d <= limit for d in (d_lower, d_upper))
    adj = adjacent_slab_pct(entry, slabs)
    out["adjacent_slab_buffer"] = float(adj) if adj is not None else None
    if adj is None:
        undefined.append("adjacent_slab_buffer")
    out["slab_boundary_exact_flag"] = slab.exact_boundary

    sc = vr.stop_calc
    stop = float(sc.stop) if sc is not None else None
    if sc is not None:
        a = sc.buffer_rupees
        b = P.BUFFER_VARIANT_B_ATR_MULT * dec(atr14)
        out["buffer_slab_source_price"] = sc.buffer_slab_source_price
        out["buffer_reference_price"] = sc.buffer_reference_price
        out["buffer_pct"] = float(sc.buffer_pct)
        out["buffer_rupees"] = float(a)
        out["buffer_variant_a_rupees"] = float(a)
        out["buffer_variant_b_rupees"] = float(b)
        out["buffer_variant_c_rupees"] = float(max(a, b))
        out["buffer_div_atr"] = _div(float(a), atr14)
    out["stop_v1"] = stop

    # §7.1 stop candidates L1/L2/L3 — logged, never selected
    stop_side_cands = vr.support_candidates if direction == P.LONG else vr.resistance_candidates
    for n in (1, 2, 3):
        if len(stop_side_cands) >= n:
            z = stop_side_cands[n - 1]
            far = z.lower_edge if direction == P.LONG else z.upper_edge
            cand_stop = float(compute_stop(direction, far, entry, tick_size, slabs).stop)
            dist = abs(entry - cand_stop)
            out[f"stop_candidate_l{n}_zone_id"] = z.final_id
            out[f"stop_candidate_l{n}"] = cand_stop
            out[f"stop_candidate_l{n}_distance_rupees"] = dist
            out[f"stop_candidate_l{n}_distance_div_atr"] = _div(dist, atr14)

    stop_distance = abs(entry - stop) if stop is not None else None
    out["stop_distance_rupees"] = stop_distance
    out["stop_distance_div_atr"] = _div(stop_distance, atr14)
    out["stop_distance_div_daily_range"] = _div(stop_distance, daily_range)
    out["stop_distance_band"] = stop_distance_band(_div(stop_distance, atr14))

    # risk / target (§5.7) and reachability diagnostics
    out["strategy_rr"] = strategy_rr
    out["risk_rupees"] = vr.risk
    out["target"] = vr.target
    target_distance = abs(vr.target - entry) if vr.target is not None else None
    out["target_distance_rupees"] = target_distance
    out["target_div_atr"] = _div(target_distance, atr14)
    out["target_div_daily_range"] = _div(target_distance, daily_range)  # target_move ÷ daily_range
    out["structural_risk"] = stop_distance

    # addendum §3 position test (diagnostic only)
    out["rr_position_limit"] = 1.0 / (1.0 + strategy_rr) * 100.0
    box_position = None
    if vr.support is not None and vr.resistance is not None:
        box_lower = vr.support.upper_edge      # locked support's NEAR edge
        box_upper = vr.resistance.lower_edge   # locked resistance's NEAR edge
        width = box_upper - box_lower
        if width > 0:
            if direction == P.LONG:
                box_position = (entry - box_lower) / width * 100.0
            else:
                box_position = (box_upper - entry) / width * 100.0
    out["box_position_pct"] = box_position
    out["position_test_pass"] = (box_position <= out["rr_position_limit"]) if box_position is not None else None

    out["decision"] = vr.decision
    out["reject_code"] = vr.reject_code
    out["diagnostic_flags"] = json.dumps(vr.diagnostic_flags)
    out["invariant_violation_detail"] = json.dumps(vr.invariant_detail) if vr.invariant_detail else None
    out["__undefined__"] = undefined
    return out


def distance_to_nearest_edge(valid_zones: Sequence[FinalZone], entry: float) -> Optional[float]:
    """Addendum §3: minimum over ALL valid final zones of |P − that zone's nearest edge|."""
    best: Optional[float] = None
    for z in valid_zones:
        d = min(abs(entry - z.lower_edge), abs(entry - z.upper_edge))
        if best is None or d < best:
            best = d
    return best
