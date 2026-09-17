"""
sr_shadow/params.py — S&R SHADOW v1.3 · FROZEN contract constants + CALIBRATION.

Contract: docs/design/secondary_filteration/sr-gate/AUTHORITATIVE_SR_SHADOW_CONTRACT_v1.3.txt
          (= v1.2 + build card §A1-§A8 + the 15-Sep-2026 addendum).

FROZEN values (v1.2 §11) are module constants and are NOT configurable.
CALIBRATION values (v1.2 §11, addendum §2) are exposed through config
(`system.sr_shadow`) and recorded on every row as `calibration_json`, so any
change to them is visible in the data. VALIDITY_VARIANT is OPEN: both variants
are always built and there is no canonical choice anywhere in this package.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal
from typing import Optional, Tuple

CONTRACT_VERSION = "v1.3"
SCHEMA_VERSION = 1  # the sr_shadow.db schema version (R10); independent of trading_system.db

# ── FROZEN (v1.2 §1, §11) ────────────────────────────────────────────────────
TF_DAILY = "1D"
TF_WEEKLY = "1W"
TIMEFRAME_RANK = {TF_DAILY: 0, TF_WEEKLY: 1}

HISTORY_YEARS = 5               # §1.1 up to 5 years, or whatever valid history returns
MIN_COMPLETED_DAILY = 15        # §1.4
MAX_LAST_DAILY_AGE_DAYS = 5     # §1.4 most recent completed daily older than 5 calendar days
SESSION_GAP_WINDOW = 15         # addendum §1: the completeness-critical window
ATR_PERIOD = 14                 # §1.3 ATR(14), Wilder, the project's canonical core.candle_math.atr
ROUND_STEP = Decimal("0.10")    # §1.5 Rama's 10-paise away-from-level rounding
TWO_CLOSE_REQUIRED = 2          # §3.6 (A3) two-consecutive-close observation variant
CONFIRM_MINUTES = 5             # §5.8 5-minute confirmation candle
EVAL_WINDOW_END = time(15, 0)   # R8: 1-minute bars beginning at/after 15:00 are not eligible
TIME_CLOSE_BAR_START = time(14, 59)  # R8: TIME_CLOSE = close of the bar beginning 14:59
BUFFER_VARIANT_B_ATR_MULT = Decimal("0.25")  # §7.2 variant B, logged only
BOUNDARY_WITHIN_PCT = 2.0       # addendum §3 boundary_within_2pct

# sides / origins / directions
ORIGIN_HIGH = "HIGH"
ORIGIN_LOW = "LOW"
SIDE_SUPPORT = "SUPPORT"
SIDE_RESISTANCE = "RESISTANCE"
LONG = "LONG"
SHORT = "SHORT"

# variants (VALIDITY_VARIANT is OPEN — both always built)
VARIANT_STRICT = "strict"
VARIANT_RECENCY = "recency"
VARIANTS = (VARIANT_STRICT, VARIANT_RECENCY)

# decisions
DECISION_SHADOW_TRADE = "SHADOW_TRADE"
DECISION_REJECTED = "REJECTED"
DECISION_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
DECISION_INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
SHADOW_DECISION_AMBIGUOUS = "AMBIGUOUS_VARIANT"

# reject taxonomy (§7.3 as amended by A7: STOP_NOT_DEFENDED is NOT a reject code)
REJECT_ENTRY_INSIDE_ZONE = "ENTRY_INSIDE_ZONE"
REJECT_STRUCTURE_UNCERTAIN = "STRUCTURE_UNCERTAIN"
REJECT_ABSENT_CLEAR_AIR = "STRUCTURE_ABSENT_CLEAR_AIR"
REJECT_ABSENT_HISTORY_LTD = "STRUCTURE_ABSENT_HISTORY_LTD"
REJECT_TARGET_BEYOND_WALL = "TARGET_BEYOND_WALL"
REJECT_CONFIRMATION_FAILED = "CONFIRMATION_FAILED"  # never emitted: ENTRY_EVENT_ONLY (R3)
REJECT_CODES = (
    REJECT_ENTRY_INSIDE_ZONE,
    REJECT_STRUCTURE_UNCERTAIN,
    REJECT_ABSENT_CLEAR_AIR,
    REJECT_ABSENT_HISTORY_LTD,
    REJECT_TARGET_BEYOND_WALL,
    REJECT_CONFIRMATION_FAILED,
)

# DATA_UNAVAILABLE sub-reasons (§1.4, A4, R8)
DU_HISTORY = "DATA_UNAVAILABLE_HISTORY"
DU_SESSION_GAP = "DATA_UNAVAILABLE_SESSION_GAP"
DU_ATR = "DATA_UNAVAILABLE_ATR"
DU_NO_CONFIRM_CANDLE = "DATA_UNAVAILABLE_NO_CONFIRM_CANDLE"
DU_NO_EVAL_WINDOW = "DATA_UNAVAILABLE_NO_EVAL_WINDOW"
DU_OUTCOME_BARS = "DATA_UNAVAILABLE_OUTCOME_BARS"

# outcome codes (§8.9, A7)
OUTCOME_TARGET_HIT = "TARGET_HIT"
OUTCOME_STOP_HIT = "STOP_HIT"
OUTCOME_AMBIGUOUS_SAME_BAR = "AMBIGUOUS_SAME_BAR"
OUTCOME_TIME_CLOSE = "TIME_CLOSE"
OUTCOME_COUNTERFACTUAL_ENTRY_INVALID = "COUNTERFACTUAL_ENTRY_INVALID"
OUTCOME_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
OUTCOME_INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
RESOLVABLE_OUTCOMES = (OUTCOME_TARGET_HIT, OUTCOME_STOP_HIT, OUTCOME_TIME_CLOSE)

# confirmation binding (§5.8, R3)
CONFIRMATION_RULE_BOUND = "ENTRY_EVENT_ONLY"
# §5.8 STEP 1/2 result, recorded so the binding is auditable. Source of the search:
# docs/audit/ENTRY_EXECUTION_FACT_FINDING_15-Sep-2026.md FF-G2/G3/G4. A rule may be
# bound only if ALL SEVEN conditions are PROVEN; anything unproven ⇒ ENTRY_EVENT_ONLY.
CONFIRMATION_BINDING_DETERMINATION = {
    "candidate": "screening.hard_gate.gate_confirm / gate_pullback via v3_chain.pb01_entry (PB-01)",
    "conditions_proven": {
        "a_deterministic": False,          # FF-G2: EXPIRED_WINDOW depends on poll wall-clock; memoized statics
        "b_reproducible": False,           # FF-G2: whether Kite revises a closed bar is NOT ESTABLISHED
        "c_only_information_by_confirming_candle": True,
        "d_no_future_or_incomplete_bar": True,
        "e_cannot_create_or_modify_structure": True,
        "f_cannot_modify_stop_target_rr_or_rescue": True,
        "g_no_order_side_effects": True,
    },
    "not_callable_unchanged": "needs a watchlist level and a 30-minute atr30 with no defined source "
                              "for an arbitrary intraday signal; LONG-only",
    "result": "ENTRY_EVENT_ONLY",
    "ruling": "addendum R3 (15-Sep-2026): acknowledged; PB-01 is not to be bound",
}
CONFIRM_STATUS_OBTAINED = "CANDLE_OBTAINED"
CONFIRM_STATUS_UNAVAILABLE = "CANDLE_UNAVAILABLE"

# session-gap check status (addendum §1)
GAP_CHECK_CHECKED = "CHECKED"
GAP_CHECK_UNADJUDICABLE = "UNADJUDICABLE_CALENDAR_COVERAGE"

UNDEFINED_REASON = "CONTRACT_FORMULA_UNDEFINED"
SIGNAL_TIMESTAMP_SOURCE = "signals.received_at"  # R4

# addendum §3 stop_distance_band — the bands v1.2 §7.4 lists, in ATR units
STOP_DISTANCE_BAND_EDGES = (0.5, 0.75, 1.0, 1.25, 1.5)
STOP_DISTANCE_BAND_LABELS = ("<0.5", "0.5-0.75", "0.75-1.0", "1.0-1.25", "1.25-1.5", ">1.5")


@dataclass(frozen=True)
class Slab:
    """One §6.5 slab. `upper` is the band's upper price edge; None = unbounded top band."""
    upper: Optional[Decimal]
    pct: Decimal


# §6.5 — STARTING CALIBRATION VALUES (step function, no interpolation).
DEFAULT_SLABS: Tuple[Slab, ...] = (
    Slab(Decimal("100"), Decimal("1.00")),
    Slab(Decimal("200"), Decimal("0.90")),
    Slab(Decimal("300"), Decimal("0.80")),
    Slab(Decimal("450"), Decimal("0.75")),
    Slab(Decimal("600"), Decimal("0.70")),
    Slab(Decimal("800"), Decimal("0.65")),
    Slab(Decimal("1100"), Decimal("0.55")),
    Slab(None, Decimal("0.45")),
)


@dataclass(frozen=True)
class Calibration:
    """CALIBRATION register (v1.2 §11). Implemented with these values; not tuned
    during the measurement period. strategy_RR is read per signal from the YAML."""
    pivot_window: int = 2
    cluster_width_pct: float = 0.50
    cluster_total_cap_pct: float = 1.00
    rejection_ratio_min: float = 0.50
    flip_closes_required: int = 1
    history_coverage_diagnostic_split_years: int = 3
    slabs: Tuple[Slab, ...] = field(default=DEFAULT_SLABS)

    @property
    def cluster_width_frac(self) -> float:
        return self.cluster_width_pct / 100.0

    @property
    def cluster_total_cap_frac(self) -> float:
        return self.cluster_total_cap_pct / 100.0

    def as_json(self) -> str:
        return json.dumps(
            {
                "pivot_window": self.pivot_window,
                "cluster_width_pct": self.cluster_width_pct,
                "cluster_total_cap_pct": self.cluster_total_cap_pct,
                "rejection_ratio_min": self.rejection_ratio_min,
                "flip_closes_required": self.flip_closes_required,
                "history_coverage_diagnostic_split_years": self.history_coverage_diagnostic_split_years,
                "slabs": [
                    {"upper": (str(s.upper) if s.upper is not None else None), "pct": str(s.pct)}
                    for s in self.slabs
                ],
            },
            sort_keys=True,
        )

    @classmethod
    def from_config(cls, cfg) -> "Calibration":
        """Build from a `system.sr_shadow` config object (SrShadowConfig)."""
        slabs = tuple(
            Slab(
                upper=(Decimal(str(s.upper)) if s.upper is not None else None),
                pct=Decimal(str(s.pct)),
            )
            for s in cfg.buffer_slabs
        )
        return cls(
            pivot_window=int(cfg.pivot_window),
            cluster_width_pct=float(cfg.cluster_width_pct),
            cluster_total_cap_pct=float(cfg.cluster_total_cap_pct),
            rejection_ratio_min=float(cfg.rejection_ratio_min),
            flip_closes_required=int(cfg.flip_closes_required),
            history_coverage_diagnostic_split_years=int(cfg.history_coverage_diagnostic_split_years),
            slabs=slabs,
        )
