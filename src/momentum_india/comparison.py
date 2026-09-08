"""Matched-window portfolio comparisons; no averaging of return streams."""

import pandas as pd

from .risk import drawdown_episode_table, performance_summary

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]


def comparison_metrics(daily, reference):
    selected = daily.loc[
        daily.return_type.eq("post_tax")
        | (daily.strategy.eq("jt_academic") & daily.return_type.eq("academic_borrow_6pct"))
    ].copy()
    selected["date"] = pd.to_datetime(selected.date)
    bounds = selected.groupby(KEYS).date.agg(["min", "max"])
    start, end = bounds["min"].max(), bounds["max"].min()
    rows = []
    expected_dates = None
    for key, group in selected.groupby(KEYS, sort=True):
        returns = group.set_index("date")["return"].sort_index().loc[start:end]
        if expected_dates is None:
            expected_dates = returns.index
        if not returns.index.equals(expected_dates) or returns.isna().any():
            raise ValueError("Comparison requires identical complete valuation dates")
        if reference.reindex(returns.index).isna().any():
            raise ValueError("Comparison cash reference has missing returns")
        row = performance_summary(returns, reference)
        wealth = returns.add(1).cumprod()
        dd = wealth.div(wealth.cummax().clip(lower=1)).sub(1)
        episodes = drawdown_episode_table(returns)
        row.update(dict(zip(KEYS, key, strict=True)))
        row.update(
            average_drawdown=float(dd.mean()),
            time_below_prior_peak=float(dd.lt(-1e-12).mean()),
            longest_underwater_trading_days=int(episodes.trading_days.max())
            if len(episodes)
            else 0,
            start_date=start,
            end_date=end,
        )
        rows.append(row)
    return pd.DataFrame(rows)
