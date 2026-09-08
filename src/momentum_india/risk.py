from __future__ import annotations

import numpy as np
import pandas as pd


def align_cash_nav(nav: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Latest available NAV on or before each session; never backfill future data."""
    return nav.reindex(nav.index.union(calendar)).sort_index().ffill().reindex(calendar)


def monthly_returns(daily_returns: pd.Series) -> pd.Series:
    values = daily_returns.dropna().sort_index()
    if not isinstance(values.index, pd.DatetimeIndex):
        raise TypeError("Monthly aggregation requires a DatetimeIndex")
    month = values.index.to_period("M")
    result = values.add(1.0).groupby(month).prod().sub(1.0)
    result.index = result.index.to_timestamp(how="end").normalize()
    return result


def historical_var_es(returns: pd.Series, confidence: float = 0.95) -> dict[str, float]:
    values = returns.dropna()
    if values.empty:
        return {"var": np.nan, "es": np.nan, "observations": 0}
    cutoff = values.quantile(1.0 - confidence)
    tail = values.loc[values.le(cutoff)]
    return {"var": -float(cutoff), "es": -float(tail.mean()), "observations": int(len(values))}


def maximum_drawdown(returns: pd.Series) -> float:
    wealth = returns.fillna(0).add(1).cumprod()
    drawdown = wealth.div(wealth.cummax().clip(lower=1.0)).sub(1)
    return float(drawdown.min())


def drawdown_episode_table(returns: pd.Series) -> pd.DataFrame:
    """Peak, trough and recovery dates for each below-prior-peak episode."""
    values = returns.sort_index().fillna(0)
    wealth = values.add(1).cumprod()
    peak, peak_date, active = 1.0, pd.NaT, None
    rows = []
    for day, value in wealth.items():
        if value >= peak * (1 - 1e-12):
            if active is not None:
                active["recovery_date"] = day
                active["calendar_days"] = (day - active["start_date"]).days
                rows.append(active)
                active = None
            peak, peak_date = max(peak, value), day
        else:
            dd = value / peak - 1
            if active is None:
                active = dict(
                    peak_date=peak_date,
                    start_date=day,
                    trough_date=day,
                    recovery_date=pd.NaT,
                    last_below_peak_date=day,
                    trading_days=0,
                    maximum_loss=dd,
                )
            active["trading_days"] += 1
            active["last_below_peak_date"] = day
            if dd < active["maximum_loss"]:
                active["maximum_loss"], active["trough_date"] = dd, day
    if active is not None:
        active["calendar_days"] = (values.index[-1] - active["start_date"]).days + 1
        rows.append(active)
    return pd.DataFrame(
        rows,
        columns=[
            "peak_date",
            "start_date",
            "trough_date",
            "recovery_date",
            "last_below_peak_date",
            "trading_days",
            "maximum_loss",
            "calendar_days",
        ],
    )


def performance_summary(
    daily_returns: pd.Series, daily_reference: pd.Series | None = None
) -> dict[str, float]:
    values = daily_returns.dropna().sort_index()
    if values.empty:
        return {
            key: np.nan
            for key in (
                "cagr",
                "annualized_volatility",
                "sharpe",
                "sortino",
                "maximum_drawdown",
                "calmar",
                "monthly_var_95",
                "monthly_es_95",
            )
        }
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1 / 365.25)
    wealth = values.add(1).prod()
    cagr = wealth ** (1 / years) - 1 if wealth > 0 else np.nan
    volatility = values.std(ddof=1) * np.sqrt(252)
    reference = (
        daily_reference.reindex(values.index).fillna(0.0) if daily_reference is not None else 0.0
    )
    excess = values - reference
    sharpe = excess.mean() / excess.std(ddof=1) * np.sqrt(252) if excess.std(ddof=1) > 0 else np.nan
    downside = np.sqrt(excess.clip(upper=0).pow(2).mean()) * np.sqrt(252)
    sortino = excess.mean() * 252 / downside if downside > 0 else np.nan
    drawdown = maximum_drawdown(values)
    monthly = monthly_returns(values)
    tail = historical_var_es(monthly, 0.95)
    return {
        "cagr": float(cagr),
        "annualized_volatility": float(volatility),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "maximum_drawdown": float(drawdown),
        "calmar": float(cagr / abs(drawdown)) if drawdown < 0 else np.nan,
        "monthly_var_95": tail["var"],
        "monthly_es_95": tail["es"],
        "observations": int(len(values)),
        "ending_wealth_multiple": float(wealth),
        "bankrupt_flag": bool(wealth <= 0 or values.le(-1).any()),
    }
