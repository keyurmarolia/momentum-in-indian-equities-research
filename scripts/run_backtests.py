"""Run the locked long-only grid and clearly separated academic JT references."""

from __future__ import annotations

import pandas as pd
import yaml

from momentum_india.config import PROJECT_ROOT
from momentum_india.portfolio import simulate_targets
from momentum_india.risk import align_cash_nav, performance_summary

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]


def main() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    processed = PROJECT_ROOT / "data" / "processed"
    market = pd.read_parquet(processed / "equity_market_panel.parquet")
    market["date"] = pd.to_datetime(market["date"])
    market_open = market.pivot(index="date", columns="symbol", values="open").sort_index()
    market_close = market.pivot(index="date", columns="symbol", values="close").sort_index()
    target = pd.read_parquet(processed / "portfolio_targets.parquet")
    events = pd.read_csv(
        processed / "portfolio_rebalance_events.csv", parse_dates=["execution_date"]
    )
    cash_frame = pd.read_csv(processed / "absl_liquid_fund_continuous.csv", parse_dates=["date"])
    cash_nav = cash_frame.set_index("date")["continuous_nav"]
    market_calendar = pd.DatetimeIndex(sorted(pd.to_datetime(market["date"]).unique()))
    market_last_date = market.groupby("symbol")["date"].max()
    delisted = pd.read_csv(
        PROJECT_ROOT / "data" / "reference" / "nse_delisted_since_2000.csv",
        parse_dates=["delisted_date"],
    )
    delisted["symbol"] = "NSE:" + delisted["nse_symbol"].astype(str) + "-EQ"
    delisted = delisted.loc[delisted["board"].eq("Main Board")]
    km_state = pd.read_parquet(processed / "km_technical_state.parquet")
    km_state["date"] = pd.to_datetime(km_state["date"])
    valid_opens = market.loc[market["open"].notna(), ["date", "symbol"]].copy()
    valid_opens["date"] = pd.to_datetime(valid_opens["date"])
    signals = km_state.loc[
        km_state.exit_signal & km_state.ema100.notna() & km_state.supertrend.notna(),
        ["date", "symbol"],
    ]
    right = valid_opens.rename(columns={"date": "execution_date"})
    km_exits = (
        pd.merge_asof(
            signals.sort_values(["date", "symbol"]),
            right.sort_values(["execution_date", "symbol"]),
            left_on="date",
            right_on="execution_date",
            by="symbol",
            direction="forward",
            allow_exact_matches=False,
        )
        .dropna(subset=["execution_date"])[["execution_date", "symbol"]]
        .drop_duplicates()
    )
    cash_daily = align_cash_nav(cash_nav, market_calendar).pct_change(fill_method=None)
    daily_outputs: list[pd.DataFrame] = []
    metrics: list[dict] = []
    trades: list[pd.DataFrame] = []
    groups = list(events.groupby(KEYS, sort=False))
    borrow_rates = config["strategies"]["jegadeesh_titman"]["borrow_cost_reference"][
        "sensitivity_annual_rates"
    ]
    target_groups = dict(tuple(target.groupby(KEYS, sort=False)))
    for number, (key, event_group) in enumerate(groups, start=1):
        selection = target_groups[key]
        symbols = selection["symbol"].unique()
        execution_dates = pd.DatetimeIndex(event_group["execution_date"].sort_values().unique())
        start = execution_dates.min()
        # Simulation consumes the pre-pivoted panels below. Keeping an empty
        # schema frame avoids copying millions of long-form rows for every cell.
        history = market.iloc[:0][["date", "symbol", "open", "close"]]
        case_calendar = market_calendar[market_calendar >= start]
        terminal = delisted.loc[delisted["symbol"].isin(symbols)].copy()
        terminal = terminal.loc[
            terminal.apply(
                lambda row: (
                    pd.notna(market_last_date.get(row["symbol"]))
                    and market_last_date.get(row["symbol"]) <= row["delisted_date"]
                ),
                axis=1,
            )
        ]
        terminal_positions = case_calendar.searchsorted(terminal["delisted_date"])
        valid_terminal = terminal_positions < len(case_calendar)
        terminal = terminal.loc[valid_terminal].copy()
        terminal["execution_date"] = case_calendar[terminal_positions[valid_terminal]].to_numpy()
        terminal = terminal.dropna(subset=["execution_date"])[["execution_date", "symbol"]]
        group_open = market_open.reindex(index=case_calendar, columns=symbols)
        group_close = market_close.reindex(index=case_calendar, columns=symbols)
        cases = (
            [("academic_raw", False, 0.0)]
            if key[0] == "jt_academic"
            else [("raw", False, 0.0), ("gross", True, 0.0)]
        )
        if key[0] == "jt_academic":
            cases += [
                (f"academic_borrow_{int(rate * 100)}pct", False, float(rate))
                for rate in borrow_rates
            ]
        for return_type, use_costs, borrow_rate in cases:
            case_selection = selection
            case_execution_dates = execution_dates
            case_history = history
            result = simulate_targets(
                case_history,
                cash_nav,
                case_selection[["execution_date", "symbol", "weight"]],
                initial_capital=float(config["portfolio"]["initial_capital_inr"]),
                apply_delivery_costs=use_costs,
                academic_borrow_rate=borrow_rate,
                execution_dates=case_execution_dates,
                maintenance_mode=key[4],
                requested_holdings_n=int(key[3]),
                forced_exit_signals=km_exits.loc[km_exits.symbol.isin(symbols)]
                if key[0] == "km_momentum"
                else None,
                terminal_events=terminal,
                valuation_dates=case_calendar,
                open_panel=group_open,
                close_panel=group_close,
            )
            daily = result.daily.reset_index()
            for column, value in zip(KEYS, key, strict=False):
                daily[column] = value
            daily["return_type"] = return_type
            daily_outputs.append(daily)
            summary = performance_summary(result.daily["return"], cash_daily)
            summary.update(dict(zip(KEYS, key, strict=False)))
            summary["return_type"] = return_type
            summary["average_long_exposure"] = result.daily["long_exposure"].mean()
            summary["average_short_exposure"] = result.daily["short_exposure"].mean()
            summary["total_borrow_cost_inr"] = result.daily["borrow_cost"].sum()
            metrics.append(summary)
            if not result.trades.empty:
                ledger = result.trades.copy()
                for column, value in zip(KEYS, key, strict=False):
                    ledger[column] = value
                ledger["return_type"] = return_type
                trades.append(ledger)
        if number % 16 == 0:
            print(f"Portfolio cells completed {number}/{len(groups)}", flush=True)
    pd.concat(daily_outputs, ignore_index=True).to_parquet(
        processed / "backtest_daily.parquet", index=False
    )
    pd.DataFrame(metrics).to_csv(processed / "backtest_metrics.csv", index=False)
    pd.concat(trades, ignore_index=True).to_parquet(processed / "trade_ledger.parquet", index=False)
    print(f"Complete: {len(metrics):,} return-series summaries")


if __name__ == "__main__":
    main()
