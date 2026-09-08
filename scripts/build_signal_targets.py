"""Build point-in-time rankings and scheduled portfolio targets."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import yaml

from momentum_india.config import PROJECT_ROOT
from momentum_india.risk import align_cash_nav
from momentum_india.schedules import rebalance_dates
from momentum_india.signals import exponential_moving_average, jensen_alpha, supertrend
from momentum_india.universe import required_mdtv_for_position


def formation_start_position(calendar, signal_date, months):
    position = int(
        calendar.searchsorted(signal_date - pd.DateOffset(months=months), side="right") - 1
    )
    if position < 0:
        raise ValueError("Formation period begins before the common market calendar")
    return position


def main():
    config = yaml.safe_load((PROJECT_ROOT / "config" / "config.yaml").read_text())
    processed = PROJECT_ROOT / "data" / "processed"
    market = pd.read_parquet(processed / "equity_market_panel.parquet")
    market["date"] = pd.to_datetime(market.date)
    benchmark = pd.read_csv(processed / "nifty50_price_index.csv", parse_dates=["date"]).set_index(
        "date"
    )
    cash = pd.read_csv(
        processed / "absl_liquid_fund_continuous.csv", parse_dates=["date"]
    ).set_index("date")
    panels = {
        f: market.pivot(index="date", columns="symbol", values=f).sort_index()
        for f in ("open", "high", "low", "close", "volume", "daily_traded_value")
    }
    calendar = pd.DatetimeIndex(benchmark.index.intersection(panels["close"].index)).sort_values()
    calendar = calendar[calendar >= cash.index.min()]
    panels = {k: v.reindex(calendar) for k, v in panels.items()}
    cash_nav = align_cash_nav(cash.continuous_nav, calendar)
    market_return = benchmark.close.reindex(calendar).pct_change(fill_method=None)
    cash_return = cash_nav.pct_change(fill_method=None)
    km = config["strategies"]["km_momentum"]
    ema = exponential_moving_average(panels["close"], km["ema_length"])
    st, bull = supertrend(
        panels["high"],
        panels["low"],
        panels["close"],
        km["supertrend_length"],
        km["supertrend_multiplier"],
    )
    state = (
        pd.concat(
            {
                "close": panels["close"].stack(future_stack=True),
                "ema100": ema.stack(future_stack=True),
                "supertrend": st.stack(future_stack=True),
                "supertrend_bullish": bull.stack(future_stack=True),
            },
            axis=1,
        )
        .reset_index()
        .rename(columns={"level_0": "date", "level_1": "symbol"})
    )
    state["above_ema_entry_buffer"] = (
        state.close >= (1 + km["minimum_close_above_ema"]) * state.ema100
    )
    state["entry_eligible"] = state.above_ema_entry_buffer & state.supertrend_bullish
    state["exit_signal"] = (
        state.ema100.notna()
        & state.supertrend.notna()
        & ((state.close < state.ema100) | (~state.supertrend_bullish))
    )
    state.to_parquet(processed / "km_technical_state.parquet", index=False)
    periods = dict(zip(config["formation"]["periods"], config["formation"]["months"], strict=False))
    liquidity_days = config["universe"]["liquidity_lookback_days"]
    min_volume = config["universe"]["minimum_volume_observations_in_126_session_window"]
    capacity = config["universe"]["capacity"]
    monthly = rebalance_dates(calendar, "1M")
    monthly = monthly[monthly >= calendar[0] + pd.DateOffset(months=max(periods.values()))]
    positions = {d: i for i, d in enumerate(calendar)}
    ranking_frames = []
    audit = []
    capacity_rows = []
    for number, day in enumerate(monthly, 1):
        pos = positions[day]
        if pos + 1 >= len(calendar):
            continue
        execution = calendar[pos + 1]
        vw = panels["volume"].iloc[max(0, pos - liquidity_days + 1) : pos + 1]
        tw = panels["daily_traded_value"].iloc[max(0, pos - liquidity_days + 1) : pos + 1]
        volume_ok = vw.notna().sum().ge(min_volume)
        mdtv = tw.fillna(0).median()
        open_ok = panels["open"].loc[execution].notna()
        for period, months in periods.items():
            start = formation_start_position(calendar, day, months)
            pw = panels["close"].iloc[start : pos + 1]
            minimum = math.ceil(len(pw) * config["formation"]["minimum_price_coverage_ratio"])
            price_ok = pw.notna().sum().ge(minimum) & pw.iloc[0].notna() & pw.iloc[-1].notna()
            prices = pw.ffill()
            returns = prices.pct_change(fill_method=None).iloc[1:]
            # Eligibility is known at the signal close; next-session quotes
            # are execution information, never a ranking-universe filter.
            pre = price_ok & volume_ok
            jumps = (
                returns.abs().gt(config["universe"]["unresolved_price_jump_threshold"]).any() & pre
            )
            valid = pre & ~jumps
            eligible = mdtv.loc[valid].sort_values(ascending=False).index
            selected = prices[eligible]
            raw = selected.iloc[-1].div(selected.iloc[0]).sub(1)
            logret = np.log(selected).diff().iloc[1:]
            vam = raw.div(logret.std(ddof=1).mul(np.sqrt(252)).replace(0, np.nan))
            alpha = jensen_alpha(
                returns[eligible],
                market_return.iloc[start + 1 : pos + 1],
                cash_return.iloc[start + 1 : pos + 1],
            )
            rank = pd.DataFrame(
                {
                    "symbol": eligible,
                    "mdtv_inr": mdtv[eligible].values,
                    "raw_momentum": raw[eligible].values,
                    "vol_adjusted": vam[eligible].values,
                    "jensen_alpha": alpha[eligible].values,
                    "ema100": ema.loc[day, eligible].values,
                    "supertrend": st.loc[day, eligible].values,
                    "supertrend_bullish": bull.loc[day, eligible].values,
                }
            )
            rank["km_entry_eligible"] = (
                (
                    panels["close"].loc[day, eligible]
                    >= (1 + km["minimum_close_above_ema"]) * ema.loc[day, eligible]
                )
                & bull.loc[day, eligible]
            ).values
            rank = rank.assign(
                formation_period=period,
                formation_months=months,
                formation_start_date=calendar[start],
                signal_date=day,
                execution_date=execution,
            )
            ranking_frames.append(rank)
            for n in config["concentration"]["holdings"]:
                threshold = required_mdtv_for_position(
                    capacity["reference_aum_inr"], n, capacity["maximum_mdtv_participation"]
                )
                capacity_rows.append(
                    {
                        "formation_period": period,
                        "signal_date": day,
                        "execution_date": execution,
                        "holdings_n": n,
                        "portfolio_aum_inr": capacity["reference_aum_inr"],
                        "maximum_mdtv_participation": capacity["maximum_mdtv_participation"],
                        "required_mdtv_inr": threshold,
                        "quality_eligible_symbols": len(eligible),
                        "capacity_eligible_symbols": int(mdtv.loc[eligible].ge(threshold).sum()),
                    }
                )
            threshold = required_mdtv_for_position(
                capacity["reference_aum_inr"],
                capacity["reference_holdings"],
                capacity["maximum_mdtv_participation"],
            )
            audit.append(
                {
                    "formation_period": period,
                    "formation_months": months,
                    "formation_start_date": calendar[start],
                    "signal_date": day,
                    "execution_date": execution,
                    "symbols_in_combined_panel": panels["close"].shape[1],
                    "price_history_eligible": int(price_ok.sum()),
                    "volume_history_eligible": int(volume_ok.sum()),
                    "execution_open_available": int(open_ok.sum()),
                    "eligible_before_jump_gate": int(pre.sum()),
                    "excluded_unresolved_price_jump": int(jumps.sum()),
                    "eligible_before_liquidity_cut": int(valid.sum()),
                    "selected_liquidity_universe": int(mdtv.loc[valid].ge(threshold).sum()),
                    "liquidity_selection_mode": "absolute_capacity",
                    "absolute_capacity_minimum_mdtv_inr": threshold,
                    "liquidity_cutoff_mdtv_inr": threshold,
                    "price_observation_minimum": minimum,
                    "price_window_sessions": len(pw),
                    "volume_observation_minimum": min_volume,
                }
            )
        if number % 24 == 0:
            print(f"Signal dates completed {number}/{len(monthly)}")
    rankings = pd.concat(ranking_frames, ignore_index=True)
    rankings.to_parquet(processed / "signal_rankings_monthly.parquet", index=False)
    pd.DataFrame(audit).to_csv(processed / "universe_rebalance_audit.csv", index=False)
    pd.DataFrame(capacity_rows).to_csv(
        processed / "universe_capacity_by_n_rebalance.csv", index=False
    )
    targets = []
    events = []
    columns = {
        "raw_momentum": "raw_momentum",
        "vol_adjusted": "vol_adjusted",
        "jensen_alpha": "jensen_alpha",
        "km_momentum": "raw_momentum",
    }
    modes = config["portfolio"]["maintenance_modes"]
    for period, period_rankings in rankings.groupby("formation_period"):
        for frequency in config["rebalancing"]["frequencies"]:
            subset = period_rankings[
                period_rankings.signal_date.isin(set(rebalance_dates(calendar, frequency)))
            ]
            for signal_day, cross in subset.groupby("signal_date"):
                execution = pd.Timestamp(cross.execution_date.iloc[0])
                for strategy in (*columns, "jt_academic"):
                    for maintenance in modes:
                        for n in config["concentration"]["holdings"]:
                            threshold = required_mdtv_for_position(
                                capacity["reference_aum_inr"],
                                n,
                                capacity["maximum_mdtv_participation"],
                            )
                            events.append(
                                {
                                    "formation_period": period,
                                    "signal_date": signal_day,
                                    "execution_date": execution,
                                    "strategy": strategy,
                                    "frequency": frequency,
                                    "holdings_n": n,
                                    "maintenance": maintenance,
                                    "required_mdtv_inr": threshold,
                                    "capacity_eligible_symbols": int(
                                        cross.mdtv_inr.ge(threshold).sum()
                                    ),
                                }
                            )
                for strategy, column in columns.items():
                    for n in config["concentration"]["holdings"]:
                        threshold = required_mdtv_for_position(
                            capacity["reference_aum_inr"], n, capacity["maximum_mdtv_participation"]
                        )
                        ordered = cross.dropna(subset=[column])
                        if strategy == "km_momentum":
                            ordered = ordered[ordered.km_entry_eligible]
                        chosen = ordered.sort_values(
                            [column, "symbol"], ascending=[False, True]
                        ).head(n)
                        for maintenance in modes:
                            block = chosen[["symbol", "execution_date"]].copy()
                            block["weight"] = 1 / n
                            block = block.assign(
                                strategy=strategy,
                                formation_period=period,
                                frequency=frequency,
                                holdings_n=n,
                                maintenance=maintenance,
                                signal_date=signal_day,
                                leg="long",
                            )
                            targets.append(block)
                for n in config["concentration"]["holdings"]:
                    threshold = required_mdtv_for_position(
                        capacity["reference_aum_inr"], n, capacity["maximum_mdtv_participation"]
                    )
                    ordered = cross.dropna(subset=["raw_momentum"]).sort_values(
                        ["raw_momentum", "symbol"], ascending=[False, True]
                    )
                    half = min(n // 2, len(ordered) // 2)
                    for leg, chosen, sign in (
                        ("long", ordered.head(half), 1.0),
                        ("short", ordered.tail(half), -1.0),
                    ):
                        for maintenance in modes:
                            block = chosen[["symbol", "execution_date"]].copy()
                            block["weight"] = sign / n
                            block = block.assign(
                                strategy="jt_academic",
                                formation_period=period,
                                frequency=frequency,
                                holdings_n=n,
                                maintenance=maintenance,
                                signal_date=signal_day,
                                leg=leg,
                            )
                            targets.append(block)
    target = pd.concat(targets, ignore_index=True)
    target.to_parquet(processed / "portfolio_targets.parquet", index=False)
    pd.DataFrame(events).to_csv(processed / "portfolio_rebalance_events.csv", index=False)
    print(f"Complete: {len(rankings):,} ranking rows and {len(target):,} target rows")


if __name__ == "__main__":
    main()
