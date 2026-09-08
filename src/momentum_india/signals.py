from __future__ import annotations

import numpy as np
import pandas as pd


def raw_momentum(close: pd.DataFrame, lookback: int = 252) -> pd.Series:
    """Trailing simple return for one rebalance cross-section."""
    if len(close) <= lookback:
        raise ValueError("Close panel must include lookback + 1 observations")
    return close.iloc[-1].div(close.iloc[-(lookback + 1)]).sub(1.0)


def volatility_adjusted_momentum(close: pd.DataFrame, lookback: int = 252) -> pd.Series:
    window = close.tail(lookback + 1)
    log_returns = np.log(window).diff().dropna(how="all")
    annualized_vol = log_returns.std(ddof=1).mul(np.sqrt(252))
    return raw_momentum(window, lookback).div(annualized_vol.replace(0, np.nan))


def jensen_alpha(
    stock_returns: pd.DataFrame,
    market_returns: pd.Series,
    daily_reference_return: pd.Series,
) -> pd.Series:
    """Daily Jensen-style intercept versus an explicit reference-return series."""
    aligned_market = market_returns.reindex(stock_returns.index)
    aligned_reference = daily_reference_return.reindex(stock_returns.index)
    market_excess = aligned_market - aligned_reference
    excess = stock_returns.sub(aligned_reference, axis=0)
    valid = excess.notna() & market_excess.notna().to_numpy()[:, None]
    count = valid.sum(axis=0).astype(float)
    y = excess.where(valid)
    sum_y = y.sum(axis=0, min_count=1)
    sum_x = valid.mul(market_excess, axis=0).sum(axis=0)
    sum_xy = y.mul(market_excess, axis=0).sum(axis=0, min_count=1)
    sum_x2 = valid.mul(market_excess.pow(2), axis=0).sum(axis=0)
    covariance_numerator = sum_xy - sum_x.mul(sum_y).div(count)
    variance_numerator = sum_x2 - sum_x.pow(2).div(count)
    beta = covariance_numerator.div(variance_numerator.replace(0, np.nan))
    alpha = sum_y.div(count) - beta.mul(sum_x.div(count))
    alpha = alpha.where(count.ge(2) & variance_numerator.gt(0))
    alpha.name = "jensen_alpha_daily"
    return alpha


def _seeded_average(values: np.ndarray, length: int, alpha: float) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) >= length:
        result[length - 1] = values[:length].mean()
        for i in range(length, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def exponential_moving_average(close: pd.DataFrame, length: int = 100) -> pd.DataFrame:
    """Observed-bar EMA, seeded with the first length closing-price mean."""
    if length <= 0:
        raise ValueError("length must be positive")
    out = close * np.nan
    for column in close:
        valid = close[column].dropna()
        out.loc[valid.index, column] = _seeded_average(valid.to_numpy(), length, 2 / (length + 1))
    return out


def _validate_ohlc(high, low, close, length):
    if length <= 0:
        raise ValueError("length must be positive")
    if not all(high.index.equals(x.index) and high.columns.equals(x.columns) for x in (low, close)):
        raise ValueError("OHLC frames must have identical index and columns")


def wilder_atr(
    high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, length: int = 10
) -> pd.DataFrame:
    """ATR seeded by the first length true ranges with an observed prior close.

    Missing exchange observations do not create synthetic bars. The first
    observed bar has no true range; the first ATR appears on bar length+1.
    """
    _validate_ohlc(high, low, close, length)
    out = close * np.nan
    for column in close:
        mask = high[column].notna() & low[column].notna() & close[column].notna()
        high_values, low_values, close_values = (
            frame.loc[mask, column].to_numpy() for frame in (high, low, close)
        )
        if len(close_values) <= length:
            continue
        tr = np.maximum.reduce(
            [
                high_values[1:] - low_values[1:],
                np.abs(high_values[1:] - close_values[:-1]),
                np.abs(low_values[1:] - close_values[:-1]),
            ]
        )
        out.loc[mask, column] = np.r_[np.nan, _seeded_average(tr, length, 1 / length)]
    return out


def supertrend(
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    length: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """HL2 bands, Wilder ATR and prior-band direction switches.

    Direction starts bullish on the first valid ATR bar. Within an unchanged
    direction the active band cannot retreat. No state is emitted on missing
    observations. Initialization is explicit rather than package-dependent.
    """
    _validate_ohlc(high, low, close, length)
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    atr = wilder_atr(high, low, close, length)
    trend = close * np.nan
    bullish = pd.DataFrame(False, index=close.index, columns=close.columns)
    for column in close:
        mask = high[column].notna() & low[column].notna() & close[column].notna()
        high_values, low_values, close_values, atr_values = (
            frame.loc[mask, column].to_numpy() for frame in (high, low, close, atr)
        )
        upper = (high_values + low_values) / 2 + multiplier * atr_values
        lower = (high_values + low_values) / 2 - multiplier * atr_values
        line = np.full(len(close_values), np.nan)
        states = np.zeros(len(close_values), dtype=bool)
        direction = True
        for i in range(length, len(close_values)):
            if i > length:
                if close_values[i] > upper[i - 1]:
                    direction = True
                elif close_values[i] < lower[i - 1]:
                    direction = False
                elif direction:
                    lower[i] = max(lower[i], lower[i - 1])
                else:
                    upper[i] = min(upper[i], upper[i - 1])
            states[i] = direction
            line[i] = lower[i] if direction else upper[i]
        trend.loc[mask, column], bullish.loc[mask, column] = line, states
    return trend, bullish
