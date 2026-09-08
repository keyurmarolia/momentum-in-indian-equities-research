"""Build local, API-free liquidity-capacity sensitivity tables."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import yaml

from momentum_india.config import PROJECT_ROOT
from momentum_india.schedules import rebalance_dates
from momentum_india.universe import required_mdtv_for_position


def main() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    processed = PROJECT_ROOT / "data" / "processed"
    market = pd.read_parquet(processed / "equity_market_panel.parquet")
    market["date"] = pd.to_datetime(market["date"])
    benchmark = pd.read_csv(processed / "nifty50_price_index.csv", parse_dates=["date"])
    cash = pd.read_csv(processed / "absl_liquid_fund_continuous.csv", parse_dates=["date"])

    close = market.pivot(index="date", columns="symbol", values="close").sort_index()
    volume = market.pivot(index="date", columns="symbol", values="volume").reindex(close.index)
    traded_value = market.pivot(
        index="date", columns="symbol", values="daily_traded_value"
    ).reindex(close.index)
    open_ = market.pivot(index="date", columns="symbol", values="open").reindex(close.index)
    calendar = pd.DatetimeIndex(pd.Index(benchmark["date"]).intersection(close.index)).sort_values()
    calendar = calendar[calendar >= cash["date"].min()]
    close, volume, traded_value, open_ = (
        close.reindex(calendar),
        volume.reindex(calendar),
        traded_value.reindex(calendar),
        open_.reindex(calendar),
    )

    universe = config["universe"]
    capacity = universe["capacity"]
    formation_periods = dict(
        zip(config["formation"]["periods"], config["formation"]["months"], strict=False)
    )
    coverage_ratio = float(config["formation"]["minimum_price_coverage_ratio"])
    liquidity_days = int(universe["liquidity_lookback_days"])
    minimum_volumes = int(universe["minimum_volume_observations_in_126_session_window"])
    jump_threshold = float(universe["unresolved_price_jump_threshold"])
    dates = rebalance_dates(calendar, "1M")
    dates = dates[dates >= calendar[0] + pd.DateOffset(months=max(formation_periods.values()))]
    positions = {date: number for number, date in enumerate(calendar)}

    scenarios = []
    for aum, holdings, participation in itertools.product(
        capacity["aum_sensitivity_inr"],
        config["concentration"]["holdings"],
        capacity["participation_sensitivity"],
    ):
        scenarios.append(
            {
                "portfolio_aum_inr": float(aum),
                "holdings_n": int(holdings),
                "maximum_mdtv_participation": float(participation),
                "required_mdtv_inr": required_mdtv_for_position(aum, holdings, participation),
            }
        )

    rows: list[dict] = []
    for day in dates:
        pos = positions[day]
        if pos + 1 >= len(calendar):
            continue
        volume_window = volume.iloc[pos - liquidity_days + 1 : pos + 1]
        traded_value_window = traded_value.iloc[pos - liquidity_days + 1 : pos + 1]
        volume_complete = volume_window.notna().sum().ge(minimum_volumes)
        for formation_period, months in formation_periods.items():
            target = day - pd.DateOffset(months=months)
            start_pos = int(calendar.searchsorted(target, side="right") - 1)
            price_window = close.iloc[start_pos : pos + 1]
            minimum_prices = math.ceil(len(price_window) * coverage_ratio)
            price_complete = price_window.notna().sum().ge(minimum_prices)
            price_complete &= price_window.iloc[0].notna() & price_window.iloc[-1].notna()
            signal_prices = price_window.ffill()
            jumps = (
                signal_prices.pct_change(fill_method=None).iloc[1:].abs().gt(jump_threshold).any()
            )
            valid = price_complete & volume_complete & ~jumps
            mdtv = traded_value_window.fillna(0.0).median().loc[valid]
            for scenario in scenarios:
                rows.append(
                    {
                        "formation_period": formation_period,
                        "signal_date": day,
                        **scenario,
                        "quality_eligible_symbols": int(valid.sum()),
                        "capacity_eligible_symbols": int(
                            mdtv.ge(scenario["required_mdtv_inr"]).sum()
                        ),
                    }
                )

    detail = pd.DataFrame(rows)
    detail.to_csv(processed / "liquidity_capacity_by_rebalance.csv", index=False)
    summary = detail.groupby(
        [
            "formation_period",
            "portfolio_aum_inr",
            "holdings_n",
            "maximum_mdtv_participation",
            "required_mdtv_inr",
        ],
        as_index=False,
    ).agg(
        first_signal_date=("signal_date", "min"),
        last_signal_date=("signal_date", "max"),
        minimum_eligible_symbols=("capacity_eligible_symbols", "min"),
        median_eligible_symbols=("capacity_eligible_symbols", "median"),
        maximum_eligible_symbols=("capacity_eligible_symbols", "max"),
        percent_dates_with_enough_names=(
            "capacity_eligible_symbols",
            lambda values: np.mean(values >= detail.loc[values.index, "holdings_n"]),
        ),
    )
    summary.to_csv(processed / "liquidity_capacity_sensitivity.csv", index=False)
    reference_n = int(capacity["reference_holdings"])
    common_rows: list[dict] = []
    for (formation_period, aum, participation), group in detail.loc[
        detail["holdings_n"].eq(reference_n)
    ].groupby(["formation_period", "portfolio_aum_inr", "maximum_mdtv_participation"]):
        for requested_n in config["concentration"]["holdings"]:
            common_rows.append(
                {
                    "formation_period": formation_period,
                    "portfolio_aum_inr": aum,
                    "requested_holdings_n": requested_n,
                    "reference_holdings_for_threshold": reference_n,
                    "maximum_mdtv_participation": participation,
                    "required_mdtv_inr": group["required_mdtv_inr"].iloc[0],
                    "first_signal_date": group["signal_date"].min(),
                    "last_signal_date": group["signal_date"].max(),
                    "minimum_eligible_symbols": group["capacity_eligible_symbols"].min(),
                    "median_eligible_symbols": group["capacity_eligible_symbols"].median(),
                    "maximum_eligible_symbols": group["capacity_eligible_symbols"].max(),
                    "percent_dates_with_enough_names": group["capacity_eligible_symbols"]
                    .ge(requested_n)
                    .mean(),
                }
            )
    common = pd.DataFrame(common_rows)
    common.to_csv(processed / "liquidity_capacity_common_universe.csv", index=False)
    print(
        f"Complete: {len(detail):,} date-scenario rows, {len(summary):,} N-specific rows, "
        f"and {len(common):,} common-universe rows"
    )


if __name__ == "__main__":
    main()
