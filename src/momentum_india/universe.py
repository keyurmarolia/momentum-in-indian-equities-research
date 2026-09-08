from __future__ import annotations

import pandas as pd

REQUIRED_MARKET_FIELDS = {"date", "symbol", "open", "high", "low", "close", "volume"}


def required_mdtv_for_position(
    portfolio_aum_inr: float,
    holdings: int,
    maximum_participation: float,
) -> float:
    """Return the minimum MDTV needed to establish one equal-weight position.

    The capacity rule asks whether a full new position can be traded while
    remaining below a stated fraction of median daily traded value. It is an
    absolute rupee-capacity test, not a rank or a comparison with a stock's own
    past volume.
    """
    if portfolio_aum_inr <= 0:
        raise ValueError("portfolio_aum_inr must be positive")
    if holdings <= 0:
        raise ValueError("holdings must be positive")
    if not 0 < maximum_participation <= 1:
        raise ValueError("maximum_participation must be between zero and one")
    return (float(portfolio_aum_inr) / int(holdings)) / float(maximum_participation)


def capacity_eligible(mdtv_inr: pd.Series, minimum_mdtv_inr: float) -> pd.Index:
    """Keep every security meeting an absolute MDTV threshold, in rank order."""
    clean = pd.to_numeric(mdtv_inr, errors="coerce").dropna().sort_values(ascending=False)
    return clean.loc[clean.ge(float(minimum_mdtv_inr))].index


def validate_market_schema(frame: pd.DataFrame) -> None:
    missing = REQUIRED_MARKET_FIELDS.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing market columns: {sorted(missing)}")
    duplicates = frame.duplicated(["date", "symbol"]).sum()
    if duplicates:
        raise ValueError(f"Found {duplicates} duplicate date-symbol rows")
