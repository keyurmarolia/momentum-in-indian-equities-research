"""Transparent adjustments for non-investable academic factor references."""

from __future__ import annotations


def prorated_borrow_cost(
    short_notional: float,
    annual_rate: float,
    holding_days: int,
    day_count: int = 365,
) -> float:
    """Illustrative simple borrow fee; not a reconstruction of observed SLB quotes."""
    if short_notional < 0 or annual_rate < 0 or holding_days < 0:
        raise ValueError("Borrow-cost inputs must be non-negative")
    return short_notional * annual_rate * holding_days / day_count
