"""Convert gross long-only simulations into annual-tax-payment return series."""

from __future__ import annotations

import pandas as pd

from momentum_india.config import PROJECT_ROOT
from momentum_india.risk import align_cash_nav, performance_summary
from momentum_india.tax_ledger import annual_equity_tax, fifo_realizations

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]


def scaled_annual_taxes(
    realized: pd.DataFrame, gross_equity: pd.Series
) -> tuple[pd.DataFrame, dict[pd.Timestamp, float]]:
    """Calculate taxes sequentially on the capital remaining after prior taxes.

    Between annual tax payments the post-tax portfolio is a constant fraction
    of the gross portfolio.  Realizations in each financial year therefore use
    the fraction known at the start of that year.  Tax is then recalculated on
    those scaled realizations so fixed rupee thresholds and loss carry-forwards
    are not incorrectly scaled as if they were proportional charges.
    """
    if realized.empty:
        return annual_equity_tax(realized), {}
    gross = gross_equity.sort_index().astype(float)
    scale = 1.0
    scaled_groups: list[pd.DataFrame] = []
    tax_by_date: dict[pd.Timestamp, float] = {}
    latest_tax = pd.DataFrame()
    for financial_year, group in sorted(
        realized.groupby("financial_year"), key=lambda pair: int(str(pair[0])[2:6])
    ):
        scaled = group.copy()
        for column in ["sale_value", "transfer_expense", "cost_basis", "realized_gain"]:
            scaled[column] = scaled[column].astype(float) * scale
        scaled_groups.append(scaled)
        latest_tax = annual_equity_tax(pd.concat(scaled_groups, ignore_index=True))
        row = latest_tax.loc[latest_tax["financial_year"].eq(financial_year)]
        if row.empty:
            continue
        start_year = int(str(financial_year)[2:6])
        fiscal_end = pd.Timestamp(start_year + 1, 3, 31)
        candidates = gross.index[gross.index <= fiscal_end]
        if candidates.empty:
            continue
        payment_date = candidates.max()
        payment = float(row.iloc[0]["total_tax"])
        tax_by_date[payment_date] = tax_by_date.get(payment_date, 0.0) + payment
        scale -= payment / float(gross.loc[payment_date])
        if scale <= 0:
            raise ValueError(f"Tax payment exhausts portfolio equity in {financial_year}")
    return latest_tax, tax_by_date


def main() -> None:
    processed = PROJECT_ROOT / "data" / "processed"
    daily = pd.read_parquet(processed / "backtest_daily.parquet")
    trades = pd.read_parquet(processed / "trade_ledger.parquet")
    metrics = pd.read_csv(processed / "backtest_metrics.csv")
    daily = daily.loc[daily.return_type.ne("post_tax")].copy()
    metrics = metrics.loc[metrics.return_type.ne("post_tax")].copy()
    market = pd.read_parquet(processed / "equity_market_panel.parquet")
    cash = pd.read_csv(
        processed / "absl_liquid_fund_continuous.csv", parse_dates=["date"]
    ).set_index("date")
    market_calendar = pd.DatetimeIndex(sorted(pd.to_datetime(market["date"]).unique()))
    cash_return = align_cash_nav(cash["continuous_nav"], market_calendar).pct_change(
        fill_method=None
    )
    fmv = (
        market.loc[market["date"].le(pd.Timestamp("2018-01-31"))]
        .sort_values("date")
        .groupby("symbol")
        .tail(1)
        .set_index("symbol")["high"]
    )
    post_daily: list[pd.DataFrame] = []
    tax_rows: list[pd.DataFrame] = []
    post_metrics: list[dict] = []
    gross_trades = trades.loc[trades["return_type"].eq("gross")]
    gross_daily = dict(tuple(daily.loc[daily.return_type.eq("gross")].groupby(KEYS, sort=False)))
    for key, group in gross_trades.groupby(KEYS, sort=False):
        realized = fifo_realizations(group, fmv)
        series = gross_daily[key].sort_values("date").copy()
        series["date"] = pd.to_datetime(series["date"])
        gross_equity = series.set_index("date")["equity"]
        initial_capital = 10_000_000.0
        taxes, tax_by_date = scaled_annual_taxes(realized, gross_equity)
        series["return_type"] = "post_tax"
        series["gross_reference_equity"] = series["equity"]
        series["gross_reference_tax"] = series["date"].map(tax_by_date).fillna(0.0)
        post_equity = initial_capital
        post_returns: list[float] = []
        post_values: list[float] = []
        paid_values: list[float] = []
        for gross_return, _gross_equity, gross_tax, day in zip(
            series["return"],
            series["gross_reference_equity"],
            series["gross_reference_tax"],
            series["date"],
            strict=False,
        ):
            before_tax = post_equity * (1 + float(gross_return))
            paid = float(gross_tax)
            after_tax = before_tax - paid
            if after_tax <= 0:
                raise ValueError(f"Tax payment exhausts portfolio equity for {key} on {day}")
            post_returns.append(after_tax / post_equity - 1)
            post_values.append(after_tax)
            paid_values.append(paid)
            post_equity = after_tax
        series["tax_paid"] = paid_values
        series["post_tax_return"] = post_returns
        series["return"] = post_returns
        series["equity"] = post_values
        series["cash_value"] *= series["equity"] / series["gross_reference_equity"]
        post_daily.append(series)
        summary = performance_summary(series.set_index("date")["return"], cash_return)
        summary.update(dict(zip(KEYS, key, strict=False)))
        summary["return_type"] = "post_tax"
        summary["total_tax_inr"] = float(series["tax_paid"].sum())
        post_metrics.append(summary)
        if not taxes.empty:
            for column, value in zip(KEYS, key, strict=False):
                taxes[column] = value
            tax_rows.append(taxes)
    pd.concat([daily, *post_daily], ignore_index=True).to_parquet(
        processed / "backtest_daily.parquet", index=False
    )
    pd.concat([metrics, pd.DataFrame(post_metrics)], ignore_index=True).to_csv(
        processed / "backtest_metrics.csv", index=False
    )
    pd.concat(tax_rows, ignore_index=True).to_csv(processed / "annual_tax_ledger.csv", index=False)
    print(f"Complete: {len(post_metrics)} post-tax long-only series")


if __name__ == "__main__":
    main()
