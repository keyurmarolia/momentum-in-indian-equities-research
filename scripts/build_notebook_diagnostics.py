"""Build auditable tables used by the descriptive result notebooks."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from momentum_india.config import PROJECT_ROOT
from momentum_india.risk import drawdown_episode_table

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]
EVENT_KEYS = KEYS + ["signal_date", "execution_date"]
SIGNAL_COLUMN = {
    "raw_momentum": "raw_momentum",
    "vol_adjusted": "vol_adjusted",
    "jensen_alpha": "jensen_alpha",
    "jt_academic": "raw_momentum",
    "km_momentum": "raw_momentum",
}


def company_lookup() -> pd.Series:
    current = pd.read_csv(PROJECT_ROOT / "data" / "reference" / "current_fyers_equity_master.csv")
    current = current[["fyers_symbol", "name"]].rename(
        columns={"fyers_symbol": "symbol", "name": "company_name"}
    )
    delisted = pd.read_csv(PROJECT_ROOT / "data" / "reference" / "nse_delisted_since_2000.csv")
    delisted["symbol"] = "NSE:" + delisted["nse_symbol"].astype(str) + "-EQ"
    names = pd.concat([current, delisted[["symbol", "company_name"]]], ignore_index=True)
    return names.dropna().drop_duplicates("symbol").set_index("symbol")["company_name"]


def build_holdings(processed: Path, tables: Path) -> pd.DataFrame:
    targets = pd.read_parquet(processed / "portfolio_targets.parquet")
    rankings = pd.read_parquet(processed / "signal_rankings_monthly.parquet")
    target_keys = KEYS + ["signal_date", "execution_date", "symbol"]
    target_lookup = targets[target_keys + ["weight", "leg"]].rename(
        columns={"weight": "target_weight", "leg": "target_leg"}
    )
    trades = pd.read_parquet(processed / "trade_ledger.parquet")
    trades["date"] = pd.to_datetime(trades["date"])
    trades = trades.loc[trades["return_type"].isin(["gross", "academic_borrow_6pct"])]
    daily = pd.read_parquet(processed / "backtest_daily.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    executions = daily.loc[
        daily["return_type"].isin(["gross", "academic_borrow_6pct"]) & daily["rebalance"],
        KEYS + ["date", "equity_before_rebalance", "transaction_cost"],
    ]
    market = pd.read_parquet(
        processed / "equity_market_panel.parquet", columns=["date", "symbol", "open", "close"]
    )
    market["date"] = pd.to_datetime(market["date"])
    raw_open = market.pivot(index="date", columns="symbol", values="open").sort_index()
    close = market.pivot(index="date", columns="symbol", values="close").sort_index().ffill()
    valuation_open = raw_open.combine_first(close.shift(1)).combine_first(close)
    actual_rows: list[dict] = []
    trade_groups = {key: group for key, group in trades.groupby(KEYS, sort=False)}
    for key, event_group in executions.groupby(KEYS, sort=False):
        trade_group = trade_groups.get(key, trades.iloc[0:0])
        units: dict[str, float] = {}
        ordered_trades = list(trade_group.sort_values("date").itertuples(index=False))
        trade_pointer = 0
        for event in event_group.sort_values("date").itertuples(index=False):
            day = pd.Timestamp(event.date)
            while (
                trade_pointer < len(ordered_trades)
                and pd.Timestamp(ordered_trades[trade_pointer].date) <= day
            ):
                trade = ordered_trades[trade_pointer]
                units[trade.symbol] = units.get(trade.symbol, 0.0) + float(trade.quantity_change)
                if abs(units[trade.symbol]) < 1e-10:
                    units.pop(trade.symbol, None)
                trade_pointer += 1
            denominator = float(event.equity_before_rebalance - event.transaction_cost)
            for symbol, quantity in sorted(units.items()):
                price = valuation_open.at[day, symbol]
                if pd.isna(price):
                    raise ValueError(f"No valuation price for {symbol} on {day.date()}")
                actual_rows.append(
                    {
                        **dict(zip(KEYS, key, strict=False)),
                        "execution_date": day,
                        "symbol": symbol,
                        "weight": quantity * float(price) / denominator,
                        "quantity": quantity,
                        "valuation_price": float(price),
                    }
                )
    holdings = pd.DataFrame(actual_rows)
    event_dates = pd.read_csv(
        processed / "portfolio_rebalance_events.csv",
        parse_dates=["signal_date", "execution_date"],
    )[KEYS + ["signal_date", "execution_date"]]
    holdings = holdings.merge(event_dates, on=KEYS + ["execution_date"], validate="many_to_one")
    holdings = holdings.merge(target_lookup, on=target_keys, how="left", validate="one_to_one")
    holdings["target_selected"] = holdings["target_weight"].notna()
    holdings["leg"] = np.where(holdings["quantity"].ge(0), "long", "short")
    holdings["execution_status"] = np.where(
        holdings["target_selected"], "selected", "awaiting_executable_exit"
    )
    rank_join = ["symbol", "formation_period", "signal_date", "execution_date"]
    rank_columns = rank_join + [
        "formation_months",
        "formation_start_date",
        "mdtv_inr",
        "raw_momentum",
        "vol_adjusted",
        "jensen_alpha",
        "ema100",
        "supertrend",
        "supertrend_bullish",
        "km_entry_eligible",
    ]
    holdings = holdings.merge(
        rankings[rank_columns], on=rank_join, how="left", validate="many_to_one"
    )
    holdings["company_name"] = holdings["symbol"].map(company_lookup())
    holdings["signal_value"] = np.nan
    for strategy, column in SIGNAL_COLUMN.items():
        mask = holdings["strategy"].eq(strategy)
        holdings.loc[mask, "signal_value"] = holdings.loc[mask, column]
    holdings["directional_rank_score"] = holdings.signal_value.where(
        holdings.leg.eq("long"), -holdings.signal_value
    )
    selected_rank = holdings["directional_rank_score"].where(holdings["target_selected"])
    holdings["signal_rank_in_selected_leg"] = (
        selected_rank.groupby([holdings[column] for column in EVENT_KEYS + ["leg"]])
        .rank(method="first", ascending=False)
        .astype("Int64")
    )
    holdings = holdings.drop(columns="directional_rank_score")
    order = EVENT_KEYS + ["leg", "signal_rank_in_selected_leg", "symbol"]
    holdings = holdings.sort_values(order).reset_index(drop=True)
    holdings.to_parquet(processed / "portfolio_holdings_at_rebalance.parquet", index=False)
    for (strategy, formation, maintenance), group in holdings.groupby(
        ["strategy", "formation_period", "maintenance"], sort=False
    ):
        group.to_csv(
            tables / f"{strategy}_{formation.lower()}_{maintenance}_portfolios.csv", index=False
        )
    return holdings


def add_churn(event: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    members = {key: set(group.symbol) for key, group in holdings.groupby(EVENT_KEYS)}
    for key, group in event.groupby(KEYS, sort=False):
        previous: set[str] = set()
        for row in group.sort_values("execution_date").itertuples():
            signal_date, execution_date = row.signal_date, row.execution_date
            current = members.get((*key, signal_date, execution_date), set())
            rows.append(
                {
                    **dict(zip(KEYS, key, strict=False)),
                    "signal_date": signal_date,
                    "execution_date": execution_date,
                    "entries": len(current - previous),
                    "exits": len(previous - current),
                    "names_retained": len(current & previous),
                    "name_retention_rate": len(current & previous) / len(previous)
                    if previous
                    else np.nan,
                }
            )
            previous = current
    return event.merge(pd.DataFrame(rows), on=EVENT_KEYS, how="left", validate="one_to_one")


def build_event_diagnostics(processed: Path, holdings: pd.DataFrame) -> pd.DataFrame:
    events = pd.read_csv(
        processed / "portfolio_rebalance_events.csv", parse_dates=["signal_date", "execution_date"]
    )
    target_summary = (
        holdings.groupby(EVENT_KEYS)
        .agg(
            actual_security_count=("symbol", "nunique"),
            target_security_count=("target_selected", "sum"),
            actual_net_equity_weight=("weight", "sum"),
            actual_gross_equity_weight=("weight", lambda x: x.abs().sum()),
            awaiting_exit_count=(
                "execution_status",
                lambda x: int(x.eq("awaiting_executable_exit").sum()),
            ),
        )
        .reset_index()
    )
    event = events.merge(target_summary, on=EVENT_KEYS, how="left")
    summary_columns = [
        "actual_security_count",
        "target_security_count",
        "actual_net_equity_weight",
        "actual_gross_equity_weight",
        "awaiting_exit_count",
    ]
    event[summary_columns] = event[summary_columns].fillna(0.0)
    long_only = ~event["strategy"].eq("jt_academic")
    event["target_cash_weight"] = np.where(
        long_only, (1.0 - event["actual_net_equity_weight"]).clip(0.0, 1.0), np.nan
    )
    event["unfilled_requested_slots"] = np.where(
        long_only,
        (event["holdings_n"] - event["target_security_count"]).clip(lower=0),
        np.nan,
    )
    event["capacity_unfilled_slots"] = np.where(
        long_only,
        (event["holdings_n"] - event["capacity_eligible_symbols"]).clip(lower=0),
        np.nan,
    )
    capacity_fillable = np.minimum(event["holdings_n"], event["capacity_eligible_symbols"])
    event["signal_unfilled_slots"] = np.where(
        long_only,
        (capacity_fillable - event["target_security_count"]).clip(lower=0),
        np.nan,
    )
    daily = pd.read_parquet(processed / "backtest_daily.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    execution = daily.loc[
        daily["rebalance"]
        & (
            daily["return_type"].eq("gross")
            | (
                daily["strategy"].eq("jt_academic")
                & daily["return_type"].eq("academic_borrow_6pct")
            )
        )
    ].copy()
    execution = execution.rename(columns={"date": "execution_date"})
    use = KEYS + [
        "execution_date",
        "equity_before_rebalance",
        "buy_value",
        "sell_value",
        "buy_orders",
        "sell_orders",
        "transaction_cost",
        "cost_brokerage",
        "cost_stt",
        "cost_exchange_transaction",
        "cost_sebi_turnover",
        "cost_ipft",
        "cost_stamp_duty",
        "cost_dp_charge",
        "cost_gst",
    ]
    event = event.merge(
        execution[use], on=KEYS + ["execution_date"], how="left", validate="one_to_one"
    )
    event["two_way_turnover"] = (event["buy_value"] + event["sell_value"]) / event[
        "equity_before_rebalance"
    ]
    event["one_way_turnover"] = event["two_way_turnover"] / 2.0
    event["cost_bps_of_turnover"] = (
        10_000 * event["transaction_cost"] / (event["buy_value"] + event["sell_value"])
    )
    event = add_churn(event, holdings)
    event.to_csv(processed / "rebalance_diagnostics.csv", index=False)
    return event


def build_cell_diagnostics(processed: Path, event: pd.DataFrame) -> pd.DataFrame:
    daily = pd.read_parquet(processed / "backtest_daily.parquet")
    long_only = daily.loc[daily["return_type"].isin(["gross", "academic_borrow_6pct"])].copy()
    long_only["cash_weight"] = (long_only["cash_value"] / long_only["equity"]).clip(lower=0.0)
    path = (
        long_only.groupby(KEYS)
        .agg(
            average_cash_weight=("cash_weight", "mean"),
            percent_days_cash_above_1pct=("cash_weight", lambda x: 100 * x.gt(0.01).mean()),
            percent_days_fully_cash=("cash_weight", lambda x: 100 * x.ge(0.99).mean()),
            average_long_exposure=("long_exposure", "mean"),
        )
        .reset_index()
    )
    e = (
        event.groupby(KEYS)
        .agg(
            rebalance_events=("execution_date", "size"),
            average_capacity_eligible_symbols=("capacity_eligible_symbols", "mean"),
            minimum_capacity_eligible_symbols=("capacity_eligible_symbols", "min"),
            average_names_held=("actual_security_count", "mean"),
            minimum_names_held=("actual_security_count", "min"),
            percent_rebalances_with_capacity_shortfall=(
                "capacity_unfilled_slots",
                lambda x: 100 * x.gt(0).mean(),
            ),
            average_capacity_unfilled_slots=("capacity_unfilled_slots", "mean"),
            average_signal_unfilled_slots=("signal_unfilled_slots", "mean"),
            average_target_cash_weight=("target_cash_weight", "mean"),
            percent_rebalances_with_cash=("target_cash_weight", lambda x: 100 * x.gt(0.001).mean()),
            average_one_way_turnover=("one_way_turnover", "mean"),
            median_one_way_turnover=("one_way_turnover", "median"),
            average_name_retention_rate=("name_retention_rate", "mean"),
            total_transaction_cost_inr=("transaction_cost", "sum"),
            total_stt_inr=("cost_stt", "sum"),
            total_brokerage_inr=("cost_brokerage", "sum"),
            total_dp_charge_inr=("cost_dp_charge", "sum"),
        )
        .reset_index()
    )
    result = path.merge(e, on=KEYS, how="outer")
    totals = long_only.groupby(KEYS).agg(
        total_transaction_cost_inr=("transaction_cost", "sum"),
        total_stt_inr=("cost_stt", "sum"),
        total_brokerage_inr=("cost_brokerage", "sum"),
        total_dp_charge_inr=("cost_dp_charge", "sum"),
        stop_exit_days=("stop_exit", "sum"),
    )
    result = result.drop(columns=[c for c in totals.columns if c in result.columns]).merge(
        totals.reset_index(), on=KEYS
    )
    result.to_csv(processed / "implementation_diagnostics.csv", index=False)
    path_rows = []
    episode_rows = []
    for key, group in daily.groupby(KEYS + ["return_type"], sort=False):
        group = group.sort_values("date")
        wealth = group["return"].fillna(0).add(1).cumprod()
        drawdown = wealth.div(wealth.cummax().clip(lower=1.0)).sub(1)
        below = drawdown.lt(-1e-12)
        runs = below.ne(below.shift()).cumsum()
        longest = int(below.groupby(runs).sum().max()) if len(below) else 0
        ep = drawdown_episode_table(group.set_index("date")["return"])
        for col, value in zip(KEYS + ["return_type"], key, strict=False):
            ep[col] = value
        episode_rows.append(ep)
        path_rows.append(
            {
                **dict(zip(KEYS + ["return_type"], key, strict=False)),
                "time_below_prior_peak": float(below.mean()),
                "average_drawdown": float(drawdown.mean()),
                "longest_underwater_trading_days": longest,
                "longest_underwater_years": longest / 252.0,
            }
        )
    pd.DataFrame(path_rows).to_csv(processed / "path_risk_diagnostics.csv", index=False)
    pd.concat(episode_rows, ignore_index=True).to_csv(
        processed / "drawdown_episodes.csv", index=False
    )
    return result


def main() -> None:
    processed = PROJECT_ROOT / "data" / "processed"
    tables = PROJECT_ROOT / "reports" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    holdings = build_holdings(processed, tables)
    event = build_event_diagnostics(processed, holdings)
    cells = build_cell_diagnostics(processed, event)
    print(
        f"Complete: {len(holdings):,} holding rows, {len(event):,} rebalance diagnostics, {len(cells):,} cell summaries"
    )


if __name__ == "__main__":
    main()
