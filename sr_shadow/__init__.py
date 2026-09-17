"""
sr_shadow/ — S&R SHADOW CONTRACT v1.3 (LOG-ONLY; GATES NOTHING).

Contract: docs/design/secondary_filteration/sr-gate/AUTHORITATIVE_SR_SHADOW_CONTRACT_v1.3.txt

For every screener-passed signal the signal path writes one immutable snapshot to
a durable spool (the ONLY work on the signal path). A background worker rebuilds
the 1D + 1W structure map from scratch, runs the §5 decision once per validity
variant (STRICT and RECENCY — VALIDITY_VARIANT is OPEN, no canonical decision),
and writes one row to data_store/sr_shadow/sr_shadow.db. The EOD evaluator
(scripts/sr_shadow_evaluate.py) fills the §8 counterfactual outcomes.

The existing score >= 60 model is the untouched control. Nothing in this package
places, modifies or cancels an order, reserves capital, changes a score, or
writes to trading_system.db. SNR-DETECTOR-V1 (sr_detector/) is a separate module;
only the shared Candle type and the rate-limited fetch closure are reused.
"""
from sr_shadow.params import CONTRACT_VERSION, SCHEMA_VERSION
from sr_shadow.runner import SrShadowService, build_sr_shadow

__all__ = ["CONTRACT_VERSION", "SCHEMA_VERSION", "SrShadowService", "build_sr_shadow"]
