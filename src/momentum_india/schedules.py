from __future__ import annotations

import pandas as pd

_MONTHS = {"1M": set(range(1, 13)), "3M": {3, 6, 9, 12}, "6M": {6, 12}, "12M": {12}}


def rebalance_dates(trading_dates: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    if frequency not in _MONTHS:
        raise ValueError(f"Unsupported frequency: {frequency}")
    dates = pd.DatetimeIndex(trading_dates).sort_values().unique()
    selected = dates[dates.month.isin(_MONTHS[frequency])]
    periods = selected.to_period("M")
    last_dates = pd.Series(selected, index=periods).groupby(level=0).max()
    return pd.DatetimeIndex(last_dates.values)
