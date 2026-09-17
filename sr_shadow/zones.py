"""
sr_shadow/zones.py — deterministic zone construction (v1.2 §2), flip state (§3,
A3), opposite-side conflicts (§3.5), the same-side sorted-sweep merge (§2.5),
touch episodes (§2.8) and zone validity under both variants (§2.7, A1).

Ordering (§3.4): preliminary zones → flip resolution on each preliminary zone →
conflict detection → same-side merge → validity. A merged zone is never
re-flipped. Every function here is pure and deterministic; the map is rebuilt
per signal (§0.6) — nothing is cached.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sr_shadow import params as P
from sr_shadow.bars import bar_date

# ─────────────────────────────────────────────────────────────────────────────
# §2.1–2.2 pivots
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Pivot:
    pivot_id: str
    timeframe: str
    origin_side: str
    date: date
    pivot_price: float
    body_price: float
    open: float
    high: float
    low: float
    close: float
    rejection_ratio: float


def rejection_ratio(origin_side: str, o: float, h: float, l: float, c: float) -> float:
    """§2.7: swing low (min(o,c) − low)/(high − low); swing high (high − max(o,c))/(high − low);
    0 when high == low."""
    rng = h - l
    if rng == 0:
        return 0.0
    if origin_side == P.ORIGIN_LOW:
        return (min(o, c) - l) / rng
    return (h - max(o, c)) / rng


def detect_pivots(bars: Sequence, timeframe: str, window: int) -> List[Pivot]:
    """§2.1 swing highs/lows with a symmetric PIVOT_WINDOW. A candle needs `window`
    candles on BOTH sides, so neither the first nor the last `window` candles can
    form a confirmed pivot."""
    out: List[Pivot] = []
    n = len(bars)
    for i in range(window, n - window):
        b = bars[i]
        neighbours = list(bars[i - window:i]) + list(bars[i + 1:i + window + 1])
        o, h, l, c = float(b.open), float(b.high), float(b.low), float(b.close)
        d = bar_date(b)
        if all(h > float(x.high) for x in neighbours):
            out.append(Pivot(
                pivot_id=f"{timeframe}:{P.ORIGIN_HIGH}:{d.isoformat()}",
                timeframe=timeframe, origin_side=P.ORIGIN_HIGH, date=d,
                pivot_price=h, body_price=max(o, c), open=o, high=h, low=l, close=c,
                rejection_ratio=rejection_ratio(P.ORIGIN_HIGH, o, h, l, c),
            ))
        if all(l < float(x.low) for x in neighbours):
            out.append(Pivot(
                pivot_id=f"{timeframe}:{P.ORIGIN_LOW}:{d.isoformat()}",
                timeframe=timeframe, origin_side=P.ORIGIN_LOW, date=d,
                pivot_price=l, body_price=min(o, c), open=o, high=h, low=l, close=c,
                rejection_ratio=rejection_ratio(P.ORIGIN_LOW, o, h, l, c),
            ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §2.3–2.4 preliminary clustering + geometry
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PrelimZone:
    zone_id: str
    timeframe: str
    origin_side: str
    members: Tuple[Pivot, ...]
    lower_edge: float
    upper_edge: float
    source_body_edge: float
    source_wick_edge: float

    @property
    def earliest_member_date(self) -> date:
        return min(p.date for p in self.members)

    @property
    def latest_member_date(self) -> date:
        return max(p.date for p in self.members)

    @property
    def default_side(self) -> str:
        return P.SIDE_RESISTANCE if self.origin_side == P.ORIGIN_HIGH else P.SIDE_SUPPORT


def cluster_pivots(pivots: Sequence[Pivot], width_frac: float, cap_frac: float) -> List[Tuple[Pivot, ...]]:
    """§2.3 single ascending pass; both conditions must hold to join; the cluster
    mean is recomputed after every addition; condition (b) is the anti-chain cap."""
    ordered = sorted(pivots, key=lambda p: (p.pivot_price, p.date, P.TIMEFRAME_RANK[p.timeframe]))
    clusters: List[Tuple[Pivot, ...]] = []
    current: List[Pivot] = []
    for p in ordered:
        if not current:
            current = [p]
            continue
        prices = [q.pivot_price for q in current]
        mean = sum(prices) / len(prices)
        cond_a = abs(p.pivot_price - mean) / mean <= width_frac
        after = prices + [p.pivot_price]
        cond_b = (max(after) - min(after)) / min(after) <= cap_frac
        if cond_a and cond_b:
            current.append(p)
        else:
            clusters.append(tuple(current))
            current = [p]
    if current:
        clusters.append(tuple(current))
    return clusters


def _geometry(origin_side: str, members: Sequence[Pivot]) -> Tuple[float, float, float, float]:
    """§2.4 preliminary geometry → (lower, upper, source_body_edge, source_wick_edge)."""
    if origin_side == P.ORIGIN_HIGH:
        lower = min(p.body_price for p in members)
        upper = max(p.pivot_price for p in members)
        return lower, upper, lower, upper
    lower = min(p.pivot_price for p in members)
    upper = max(p.body_price for p in members)
    return lower, upper, upper, lower


def build_prelim_zones(pivots: Sequence[Pivot], width_frac: float, cap_frac: float) -> List[PrelimZone]:
    """Preliminary zones per origin_side per timeframe (§2.3), with §2.4 geometry."""
    out: List[PrelimZone] = []
    for tf in (P.TF_DAILY, P.TF_WEEKLY):
        for origin in (P.ORIGIN_HIGH, P.ORIGIN_LOW):
            group = [p for p in pivots if p.timeframe == tf and p.origin_side == origin]
            for k, members in enumerate(cluster_pivots(group, width_frac, cap_frac)):
                lower, upper, body_edge, wick_edge = _geometry(origin, members)
                out.append(PrelimZone(
                    zone_id=f"{tf}-{origin}-{k:04d}",
                    timeframe=tf, origin_side=origin,
                    members=tuple(sorted(members, key=lambda m: m.date)),
                    lower_edge=lower, upper_edge=upper,
                    source_body_edge=body_edge, source_wick_edge=wick_edge,
                ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §3.1–3.3 + §3.6 (A3) flip state — preliminary zones only
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FlipResult:
    side: str
    transitions: Tuple[Tuple[date, str, str], ...]


def resolve_flip(zone: PrelimZone, daily: Sequence, closes_required: int) -> FlipResult:
    """Iterate completed daily candles strictly after the zone's latest member date.

    On the SUPPORT side a qualifying close is STRICTLY BELOW lower_edge (→ RESISTANCE);
    on the RESISTANCE side a qualifying close is STRICTLY ABOVE upper_edge (→ SUPPORT).
    For ORIGIN HIGH this is exactly "flip on a close above upper, revert only on a
    close below lower"; for ORIGIN LOW exactly the mirror (§3.1).
    `closes_required` qualifying closes must be CONSECUTIVE daily candles; any
    non-qualifying close — including a close exactly on an edge or inside the
    zone — resets the counter to zero (§3.6). The counter also resets after a
    transition."""
    side = zone.default_side
    count = 0
    transitions: List[Tuple[date, str, str]] = []
    after = zone.latest_member_date
    for c in daily:
        d = bar_date(c)
        if d <= after:
            continue
        close = float(c.close)
        if side == P.SIDE_SUPPORT:
            qualifies = close < zone.lower_edge
        else:
            qualifies = close > zone.upper_edge
        if qualifies:
            count += 1
            if count >= closes_required:
                new_side = P.SIDE_RESISTANCE if side == P.SIDE_SUPPORT else P.SIDE_SUPPORT
                transitions.append((d, side, new_side))
                side = new_side
                count = 0
        else:
            count = 0
    return FlipResult(side=side, transitions=tuple(transitions))


# ─────────────────────────────────────────────────────────────────────────────
# §3.5 opposite-side overlap = contradiction
# ─────────────────────────────────────────────────────────────────────────────


def intervals_overlap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> bool:
    """Closed intervals (§2.4): touching at an edge counts as overlap."""
    return a_lo <= b_hi and b_lo <= a_hi


def detect_conflicts(zones: Sequence[PrelimZone], sides: Dict[str, str]) -> Set[str]:
    flagged: Set[str] = set()
    zs = list(zones)
    for i in range(len(zs)):
        a = zs[i]
        for j in range(i + 1, len(zs)):
            b = zs[j]
            if sides[a.zone_id] == sides[b.zone_id]:
                continue
            if intervals_overlap(a.lower_edge, a.upper_edge, b.lower_edge, b.upper_edge):
                flagged.add(a.zone_id)
                flagged.add(b.zone_id)
    return flagged


# ─────────────────────────────────────────────────────────────────────────────
# §2.8 touch episodes
# ─────────────────────────────────────────────────────────────────────────────


def count_touch_episodes(lower: float, upper: float, daily: Sequence) -> int:
    """Interaction episodes over the FULL completed daily history (§2.8, frozen).
    A candle interacts iff high >= lower AND low <= upper (inclusive); a maximal
    run of consecutive interacting candles is one episode."""
    episodes = 0
    in_episode = False
    for c in daily:
        interacts = float(c.high) >= lower and float(c.low) <= upper
        if interacts and not in_episode:
            episodes += 1
        in_episode = interacts
    return episodes


# ─────────────────────────────────────────────────────────────────────────────
# §2.5 same-side merge (order-independent sorted sweep)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FinalZone:
    final_id: str
    side: str
    lower_edge: float
    upper_edge: float
    sources: Tuple[PrelimZone, ...]
    source_flips_1close: Tuple[FlipResult, ...]
    source_flips_2close: Tuple[FlipResult, ...]
    source_conflict_flags: Tuple[bool, ...]
    touch_count: int

    @property
    def members(self) -> Tuple[Pivot, ...]:
        seen = {}
        for s in self.sources:
            for m in s.members:
                seen[m.pivot_id] = m
        return tuple(sorted(seen.values(), key=lambda m: (m.date, m.timeframe, m.origin_side)))

    @property
    def pivot_count(self) -> int:
        return len(self.members)

    @property
    def daily_member_count(self) -> int:
        return sum(1 for m in self.members if m.timeframe == P.TF_DAILY)

    @property
    def weekly_member_count(self) -> int:
        return sum(1 for m in self.members if m.timeframe == P.TF_WEEKLY)

    @property
    def source_timeframes(self) -> Tuple[str, ...]:
        return tuple(s.timeframe for s in self.sources)

    @property
    def timeframes(self) -> Tuple[str, ...]:
        return tuple(sorted(set(self.source_timeframes), key=lambda t: P.TIMEFRAME_RANK[t]))

    @property
    def cross_timeframe_merge_flag(self) -> bool:
        return len(set(self.source_timeframes)) > 1

    @property
    def mixed_origin_flag(self) -> bool:
        return len({s.origin_side for s in self.sources}) > 1

    @property
    def structure_uncertain_flag(self) -> bool:
        """R9/S8: a final zone carries the conflict diagnostic if ANY source is flagged."""
        return any(self.source_conflict_flags)

    @property
    def latest_member_date(self) -> date:
        return max(m.date for m in self.members)

    def near_far(self, entry: float) -> Tuple[Optional[float], Optional[float]]:
        """§2.4 near/far from the approach direction; (None, None) when the zone is
        not entirely below or entirely above the entry."""
        if self.upper_edge < entry:
            return self.upper_edge, self.lower_edge
        if self.lower_edge > entry:
            return self.lower_edge, self.upper_edge
        return None, None

    def flip_transitions_json(self) -> str:
        """Addendum §3: JSON array, chronological, of {date, from_side, to_side}."""
        items = []
        for idx, fr in enumerate(self.source_flips_1close):
            for (d, frm, to) in fr.transitions:
                items.append((d, idx, {"date": d.isoformat(), "from_side": frm, "to_side": to}))
        items.sort(key=lambda t: (t[0], t[1]))
        return json.dumps([t[2] for t in items])

    def flip_result_1close(self) -> str:
        return self.side

    def flip_result_2close(self) -> Optional[str]:
        """The two-close side when every source zone agrees; None when merged sources
        disagree (no formula defines a merged zone's two-close result)."""
        values = {fr.side for fr in self.source_flips_2close}
        return values.pop() if len(values) == 1 else None


def merge_same_side(
    zones: Sequence[PrelimZone],
    flips_1: Dict[str, FlipResult],
    flips_2: Dict[str, FlipResult],
    conflicts: Set[str],
    daily: Sequence,
) -> List[FinalZone]:
    """§2.5: pool same CURRENT side across timeframes; sort by (lower_edge,
    upper_edge, earliest_member_date, timeframe_rank); one ascending sweep with a
    running maximum upper edge; merge each connected component once; union
    geometry (§2.4). Opposite-side zones are never merged."""
    finals: List[FinalZone] = []
    for side in (P.SIDE_SUPPORT, P.SIDE_RESISTANCE):
        pool = [z for z in zones if flips_1[z.zone_id].side == side]
        pool.sort(key=lambda z: (z.lower_edge, z.upper_edge, z.earliest_member_date,
                                 P.TIMEFRAME_RANK[z.timeframe], z.zone_id))
        components: List[List[PrelimZone]] = []
        running_max: Optional[float] = None
        for z in pool:
            if components and running_max is not None and z.lower_edge <= running_max:
                components[-1].append(z)
                running_max = max(running_max, z.upper_edge)
            else:
                components.append([z])
                running_max = z.upper_edge
        for comp in components:
            lower = min(z.lower_edge for z in comp)
            upper = max(z.upper_edge for z in comp)
            finals.append(FinalZone(
                final_id=f"{side[0]}:" + "+".join(z.zone_id for z in comp),
                side=side, lower_edge=lower, upper_edge=upper,
                sources=tuple(comp),
                source_flips_1close=tuple(flips_1[z.zone_id] for z in comp),
                source_flips_2close=tuple(flips_2[z.zone_id] for z in comp),
                source_conflict_flags=tuple(z.zone_id in conflicts for z in comp),
                touch_count=count_touch_episodes(lower, upper, daily),
            ))
    finals.sort(key=lambda f: (f.lower_edge, f.upper_edge, f.final_id))
    return finals


# ─────────────────────────────────────────────────────────────────────────────
# §2.7 validity (STRICT / RECENCY with A1)
# ─────────────────────────────────────────────────────────────────────────────


def latest_pivot_ids(pivots: Sequence[Pivot]) -> Dict[Tuple[str, str], str]:
    """The most recent pivot per (timeframe, origin_side)."""
    best: Dict[Tuple[str, str], Pivot] = {}
    for p in pivots:
        key = (p.timeframe, p.origin_side)
        cur = best.get(key)
        if cur is None or p.date > cur.date:
            best[key] = p
    return {k: v.pivot_id for k, v in best.items()}


def valid_strict(zone: FinalZone) -> bool:
    return zone.touch_count >= 2


def valid_recency(
    zone: FinalZone, latest_ids: Dict[Tuple[str, str], str], rejection_ratio_min: float
) -> Tuple[bool, Optional[str]]:
    """A1: touch_count >= 2, OR touch_count == 1 AND at least ONE SOURCE zone has
    exactly one member pivot that is the most recent pivot on THAT source zone's
    origin_side within THAT source zone's timeframe, with rejection_ratio >=
    REJECTION_RATIO_MIN. Evaluated per source zone — never on merged members.
    Returns (valid, recency_source_zone_id)."""
    if zone.touch_count >= 2:
        return True, None
    if zone.touch_count != 1:
        return False, None
    for s in zone.sources:
        if len(s.members) != 1:
            continue
        pivot = s.members[0]
        if latest_ids.get((s.timeframe, s.origin_side)) != pivot.pivot_id:
            continue
        if pivot.rejection_ratio >= rejection_ratio_min:
            return True, s.zone_id
    return False, None


# ─────────────────────────────────────────────────────────────────────────────
# the full per-signal map (§3.4 order)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StructureMap:
    pivots: Tuple[Pivot, ...]
    prelim_zones: Tuple[PrelimZone, ...]
    flips_1close: Dict[str, FlipResult]
    flips_2close: Dict[str, FlipResult]
    conflicts: frozenset
    final_zones: Tuple[FinalZone, ...]
    latest_ids: Dict[Tuple[str, str], str]


def build_structure_map(daily: Sequence, weekly: Sequence, calibration: P.Calibration) -> StructureMap:
    pivots = (detect_pivots(daily, P.TF_DAILY, calibration.pivot_window)
              + detect_pivots(weekly, P.TF_WEEKLY, calibration.pivot_window))
    prelim = build_prelim_zones(pivots, calibration.cluster_width_frac, calibration.cluster_total_cap_frac)
    flips_1 = {z.zone_id: resolve_flip(z, daily, calibration.flip_closes_required) for z in prelim}
    flips_2 = {z.zone_id: resolve_flip(z, daily, P.TWO_CLOSE_REQUIRED) for z in prelim}
    conflicts = detect_conflicts(prelim, {k: v.side for k, v in flips_1.items()})
    finals = merge_same_side(prelim, flips_1, flips_2, conflicts, daily)
    return StructureMap(
        pivots=tuple(pivots), prelim_zones=tuple(prelim),
        flips_1close=flips_1, flips_2close=flips_2,
        conflicts=frozenset(conflicts), final_zones=tuple(finals),
        latest_ids=latest_pivot_ids(pivots),
    )
