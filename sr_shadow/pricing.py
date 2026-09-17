"""
sr_shadow/pricing.py — §6 baseline structural stop, §6.5 slab table, §1.5
rounding, and the A7 stop invariant.

All stop arithmetic is Decimal so the 10-paise rounding and the tick lattice are
exact. The buffer is a percentage of the STRUCTURAL LEVEL (the locked zone's far
edge) selected by the slab of the ENTRY price (§6.4) — never a percentage of the
entry price, never a percentage of ATR. This is NOT the entry-slippage
allowance: it shares no code path, no config key and no value with it (§6.5).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Optional, Sequence

from sr_shadow import params as P


def dec(x) -> Decimal:
    """Exact decimal of a price as written (shortest float repr)."""
    if isinstance(x, Decimal):
        return x
    return Decimal(repr(float(x)))


@dataclass(frozen=True)
class SlabPick:
    index: int
    pct: Decimal
    lower: Optional[Decimal]  # None when the band has no lower slab boundary
    upper: Optional[Decimal]  # None when the band has no upper slab boundary
    exact_boundary: bool


def pick_slab(price: float, slabs: Sequence[P.Slab]) -> SlabPick:
    """§6.5 step function. Bands, lowest first: [0, u1), [u1, u2), …, the LAST
    bounded band closed at its upper edge ("800–1100" includes 1100), then
    (u_last, ∞) ("above 1100"). `exact_boundary` flags a price exactly on a slab
    boundary so any such row is visible."""
    p = dec(price)
    bounded = [s for s in slabs if s.upper is not None]
    top = [s for s in slabs if s.upper is None]
    boundaries = {s.upper for s in bounded}
    exact = p in boundaries
    lower: Optional[Decimal] = None
    for i, s in enumerate(bounded):
        last_bounded = i == len(bounded) - 1
        inside = p <= s.upper if last_bounded else p < s.upper
        if inside:
            return SlabPick(index=i, pct=s.pct, lower=lower, upper=s.upper, exact_boundary=exact)
        lower = s.upper
    if not top:
        raise ValueError("slab table has no unbounded top band")
    return SlabPick(index=len(bounded), pct=top[0].pct, lower=lower, upper=None, exact_boundary=exact)


def round_stop(candidate: Decimal, direction: str, tick: Decimal) -> Decimal:
    """§1.5, exactly: (1) round to the nearest 0.10 AWAY from the level — DOWN for
    a LONG stop, UP for a SHORT stop; (2) enforce the instrument's tick lattice;
    (3) if (1) is not a valid tick, move FURTHER AWAY to the next valid tick."""
    if tick <= 0:
        raise ValueError(f"invalid tick size {tick!r}")
    mode = ROUND_FLOOR if direction == P.LONG else ROUND_CEILING
    step1 = (candidate / P.ROUND_STEP).to_integral_value(rounding=mode) * P.ROUND_STEP
    if (step1 / tick) == (step1 / tick).to_integral_value():
        return step1
    return (step1 / tick).to_integral_value(rounding=mode) * tick


@dataclass(frozen=True)
class StopCalc:
    direction: str
    far_edge: float
    buffer_slab_source_price: float
    buffer_reference_price: float
    buffer_pct: Decimal
    buffer_rupees: Decimal
    candidate_stop: Decimal
    stop: Decimal
    slab: SlabPick


def compute_stop(direction: str, far_edge: float, entry: float, tick_size: float,
                 slabs: Sequence[P.Slab]) -> StopCalc:
    """§6.2 LONG: far edge − buffer, rounded DOWN; §6.3 SHORT: far edge + buffer,
    rounded UP. buffer_rupees = buffer_pct × buffer_reference_price (the level)."""
    slab = pick_slab(entry, slabs)
    level = dec(far_edge)
    buffer_rupees = slab.pct / Decimal(100) * level
    if direction == P.LONG:
        candidate = level - buffer_rupees
    else:
        candidate = level + buffer_rupees
    stop = round_stop(candidate, direction, dec(tick_size))
    return StopCalc(
        direction=direction, far_edge=float(far_edge),
        buffer_slab_source_price=float(entry), buffer_reference_price=float(far_edge),
        buffer_pct=slab.pct, buffer_rupees=buffer_rupees,
        candidate_stop=candidate, stop=stop, slab=slab,
    )


def stop_invariant_holds(direction: str, stop: Decimal, far_edge: float) -> bool:
    """A7 invariant: LONG stop strictly BELOW the support far edge; SHORT stop
    strictly ABOVE the resistance far edge. A failure is a build defect."""
    level = dec(far_edge)
    return stop < level if direction == P.LONG else stop > level


def adjacent_slab_pct(price: float, slabs: Sequence[P.Slab]) -> Optional[Decimal]:
    """Addendum §3: the buffer percentage the NEARER neighbouring slab would have
    produced. None when the two neighbours are exactly equidistant."""
    pick = pick_slab(price, slabs)
    p = dec(price)
    ordered = list(slabs)
    lower_pct = ordered[pick.index - 1].pct if pick.index > 0 else None
    upper_pct = ordered[pick.index + 1].pct if pick.index + 1 < len(ordered) else None
    d_lower = (p - pick.lower) if pick.lower is not None else None
    d_upper = (pick.upper - p) if pick.upper is not None else None
    if d_lower is None and d_upper is None:
        return None
    if d_lower is None:
        return upper_pct
    if d_upper is None:
        return lower_pct
    if d_lower < d_upper:
        return lower_pct
    if d_upper < d_lower:
        return upper_pct
    return None
