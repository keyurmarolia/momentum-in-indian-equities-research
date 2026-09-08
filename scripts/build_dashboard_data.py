"""Export cached research into lazy-loaded, static dashboard files. No network calls."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from momentum_india.dashboard_data import KEYS, finite_json, position_history
from momentum_india.risk import align_cash_nav, drawdown_episode_table, performance_summary

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"
OUT = ROOT / "dashboard/public/data"
LABELS = dict(
    raw_momentum="Raw momentum",
    vol_adjusted="Volatility-adjusted momentum",
    jensen_alpha="Jensen alpha",
    km_momentum="KM momentum",
    jt_academic="Jegadeesh–Titman · academic",
)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(finite_json(data), separators=(",", ":"), allow_nan=False).encode()
    if path.parent.name in ["stocks", "experiments"]:
        path.with_suffix(".json.gz").write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
    else:
        path.write_bytes(payload)


def main(limit=0, skip_prices=False):
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(P / "backtest_metrics.csv").merge(
        pd.read_csv(P / "path_risk_diagnostics.csv"),
        on=KEYS + ["return_type"],
        validate="one_to_one",
    )
    holdings = pd.read_parquet(P / "portfolio_holdings_at_rebalance.parquet")
    trades = pd.read_parquet(
        P / "trade_ledger.parquet",
        filters=[("return_type", "in", ["gross", "academic_borrow_6pct"])],
    )
    daily = pd.read_parquet(
        P / "backtest_daily.parquet",
        columns=KEYS
        + [
            "return_type",
            "date",
            "equity",
            "cash_value",
            "borrow_cost",
            "transaction_cost",
            "return",
            "rebalance",
            "equity_before_rebalance",
        ],
    )
    events = pd.read_csv(
        P / "rebalance_diagnostics.csv", parse_dates=["signal_date", "execution_date"]
    )
    symbols = sorted(set(trades.symbol) | set(holdings.symbol))
    ids = {symbol: str(i) for i, symbol in enumerate(symbols)}
    names = (
        holdings.dropna(subset=["company_name"])
        .drop_duplicates("symbol")
        .set_index("symbol")
        .company_name.to_dict()
    )
    print(f"Loading cached prices for {len(symbols):,} traded securities", flush=True)
    market = pd.read_parquet(
        P / "equity_market_panel.parquet",
        columns=["date", "symbol", "open", "high", "low", "close", "isin"],
        filters=[("symbol", "in", symbols)],
    )
    market = market.sort_values(["symbol", "date"])
    if market.duplicated(["symbol", "date"]).any():
        raise ValueError("Ambiguous security-day rows")
    price_groups = {s: g.set_index("date") for s, g in market.groupby("symbol", sort=False)}
    del market
    technical = None
    if not skip_prices:
        technical = pd.read_parquet(
            P / "km_technical_state.parquet",
            columns=["date", "symbol", "close", "ema100", "supertrend", "supertrend_bullish"],
            filters=[("symbol", "in", symbols)],
        )
        technical = technical[technical.close.notna()].drop(columns="close")
        tech_groups = {s: g.set_index("date") for s, g in technical.groupby("symbol", sort=False)}
    metadata = {}
    for symbol, g in price_groups.items():
        sid = ids[symbol]
        metadata[sid] = dict(
            symbol=symbol,
            ticker=symbol.removeprefix("NSE:").removesuffix("-EQ"),
            name=names.get(symbol, symbol),
            start=g.index.min(),
            end=g.index.max(),
            multiple_isins=bool(g["isin"].dropna().nunique() > 1),
        )
        if not skip_prices:
            merged = g.join(
                tech_groups.get(
                    symbol, pd.DataFrame(columns=["ema100", "supertrend", "supertrend_bullish"])
                ),
                rsuffix="_technical",
            )
            columns = ["open", "high", "low", "close", "ema100", "supertrend", "supertrend_bullish"]
            rows = merged[columns].reset_index()
            rows["date"] = rows["date"].dt.strftime("%Y-%m-%d")
            for col in columns[:-1]:
                rows[col] = rows[col].round(8)
            write(
                OUT / "stocks" / f"{sid}.json",
                dict(columns=["date"] + columns, rows=rows.values.tolist()),
            )
    del technical
    if not skip_prices:
        del tech_groups
    from plotly.offline import get_plotlyjs

    (ROOT / "dashboard/public/plotly.min.js").write_text(get_plotlyjs())
    print("Price shards ready; reconciling experiments", flush=True)
    trades["fee"] = trades["allocated_cost"].fillna(0.0)
    groups = {key: g for key, g in trades.groupby(KEYS, sort=False)}
    hg = {key: g for key, g in holdings.groupby(KEYS, sort=False)}
    eg = {key: g for key, g in events.groupby(KEYS, sort=False)}
    dg = {key: g for key, g in daily.groupby(KEYS, sort=False)}
    benchmark = (
        pd.read_csv(P / "nifty50_price_index.csv", parse_dates=["date"])
        .set_index("date")
        .close.pct_change(fill_method=None)
    )
    cash = (
        pd.read_csv(P / "absl_liquid_fund_continuous.csv", parse_dates=["date"])
        .set_index("date")
        .continuous_nav
    )
    # Accumulate weekend/holiday NAV growth into the next market session.
    cash_return = align_cash_nav(cash, benchmark.index).pct_change(fill_method=None)
    catalog = []
    checks = []
    for number, (key, m) in enumerate(metrics.groupby(KEYS, sort=False)):
        if limit and number >= limit:
            break
        eid = "--".join(str(x) for x in key)
        academic = key[0] == "jt_academic"
        layer = "academic_borrow_6pct" if academic else "gross"
        ds = dg[key]
        canonical = ds[ds.return_type.eq(layer)].sort_values("date").set_index("date")
        ts = groups.get(key, trades.iloc[:0]).sort_values(["date", "symbol"])
        allocated = ts.groupby("date").fee.sum().reindex(canonical.index, fill_value=0)
        fee_error = float((allocated - canonical.transaction_cost).abs().max())
        if fee_error > max(0.001, canonical.transaction_cost.max() * 1e-8):
            raise ValueError(f"Fee mismatch {eid}: {fee_error}")
        dates = canonical.index
        all_borrow = np.zeros(len(dates))
        histories = {}
        for symbol, st in ts.groupby("symbol", sort=False):
            prices = price_groups[symbol]
            known = prices[prices.index <= dates[-1]].close.dropna()
            records = st[["date", "price", "quantity_change", "fee", "exit_reason"]].copy()
            records["date"] = records.date.dt.strftime("%Y-%m-%d")
            history = position_history(
                records.to_dict("records"),
                float(known.iloc[-1]),
                known.index[-1].strftime("%Y-%m-%d"),
            )
            if academic:
                units = (
                    st.groupby("date")
                    .quantity_change.sum()
                    .cumsum()
                    .reindex(dates)
                    .ffill()
                    .fillna(0)
                    .to_numpy()
                )
                close = (
                    prices.close.reindex(prices.index.union(dates))
                    .sort_index()
                    .ffill()
                    .reindex(dates)
                    .to_numpy()
                )
                gaps = dates.to_series().diff().dt.days.fillna(0).to_numpy()
                borrowing = np.nan_to_num(np.maximum(-units, 0) * close * 0.06 * gaps / 365)
                all_borrow += borrowing
                for episode in history["episodes"]:
                    active = dates >= pd.Timestamp(episode["entry"])
                    if episode["exit"]:
                        active &= dates < pd.Timestamp(episode["exit"])
                    episode["borrow"] = (
                        float(borrowing[active].sum()) if episode["direction"] < 0 else 0.0
                    )
            for episode in history["episodes"]:
                episode["net_pnl"] = episode["pnl"] - episode["borrow"]
            # Reconcile each symbol's net signed cash flows and ending position.
            q = float(st.quantity_change.sum())
            direct = -float(st.trade_value.sum()) + q * float(known.iloc[-1]) - float(st.fee.sum())
            error = abs(sum(e["pnl"] for e in history["episodes"]) - direct)
            if error > max(0.02, abs(direct) * 1e-8):
                raise ValueError(f"Position mismatch {eid} {symbol}: {error}")
            histories[ids[symbol]] = history
        borrow_error = float(np.max(np.abs(all_borrow - canonical.borrow_cost.to_numpy())))
        if borrow_error > max(0.01, canonical.borrow_cost.max() * 1e-8):
            raise ValueError(f"Borrow mismatch {eid}: {borrow_error}")
        membership = {day: g for day, g in hg.get(key, holdings.iloc[:0]).groupby("execution_date")}
        ordered = list(ts.itertuples(index=False))
        pointer = 0
        units = {}
        snapshots = []
        prior_date = None
        for event in eg[key].sort_values("execution_date").itertuples(index=False):
            day = event.execution_date
            while pointer < len(ordered) and ordered[pointer].date < day:
                t = ordered[pointer]
                units[t.symbol] = units.get(t.symbol, 0) + t.quantity_change
                pointer += 1
            before = units.copy()
            while pointer < len(ordered) and ordered[pointer].date <= day:
                t = ordered[pointer]
                units[t.symbol] = units.get(t.symbol, 0) + t.quantity_change
                pointer += 1
            capital = (
                canonical.loc[day, "equity_before_rebalance"]
                - canonical.loc[day, "transaction_cost"]
            )
            members = []
            for row in membership.get(day, holdings.iloc[:0]).itertuples(index=False):
                q = units.get(row.symbol, 0)
                if abs(q) < 1e-8:
                    continue
                old = before.get(row.symbol, 0)
                state = (
                    "awaiting exit"
                    if not row.target_selected
                    else (
                        "new"
                        if abs(old) < 1e-8 or old * q < 0
                        else (
                            "increased"
                            if abs(q) > abs(old) + 1e-7
                            else ("trimmed" if abs(q) < abs(old) - 1e-7 else "retained")
                        )
                    )
                )
                members.append(
                    dict(
                        id=ids[row.symbol],
                        weight=row.weight,
                        quantity=q,
                        value=row.weight * capital,
                        rank=row.signal_rank_in_selected_leg,
                        signal=row.signal_value,
                        mdtv=row.mdtv_inr,
                        leg=row.leg,
                        status=state,
                        target_selected=bool(row.target_selected),
                    )
                )
            # Check actual membership is complete, rather than silently losing carried holdings.
            actual = {s for s, q in units.items() if abs(q) > 1e-7}
            reported = {symbols[int(r["id"])] for r in members}
            if actual != reported:
                raise ValueError(f"Membership mismatch {eid} {day}: {actual ^ reported}")
            departures = []
            for sid, history in histories.items():
                for e in history["episodes"]:
                    if (
                        e["exit"]
                        and (prior_date is None or e["exit"] > prior_date)
                        and e["exit"] <= str(day.date())
                    ):
                        departures.append(
                            dict(
                                id=sid,
                                date=e["exit"],
                                reason=next(
                                    t["reason"]
                                    for t in reversed(history["trades"])
                                    if t["episode"] == e["id"]
                                ),
                            )
                        )
            snapshots.append(
                dict(
                    date=day,
                    signal_date=event.signal_date,
                    capital=capital,
                    cash=capital - sum(r["value"] for r in members),
                    holdings=members,
                    departures=departures,
                    fees=canonical.loc[day, "transaction_cost"],
                    eligible=event.capacity_eligible_symbols,
                    threshold=event.required_mdtv_inr,
                    turnover=event.two_way_turnover,
                )
            )
            prior_date = str(day.date())
        curves = {}
        for rt, g in ds.groupby("return_type"):
            g = g.sort_values("date")
            curves[rt] = g.equity.div(1e7).round(9).tolist()
        b = benchmark.reindex(dates).fillna(0)
        curves["benchmark"] = (1 + b).cumprod().round(9).tolist()
        bm = performance_summary(b, cash_return)
        w = (1 + b).cumprod()
        underwater = w.div(w.cummax().clip(lower=1)).sub(1) < -1e-12
        episodes = drawdown_episode_table(b)
        bm.update(
            average_drawdown=float(w.div(w.cummax().clip(lower=1)).sub(1).mean()),
            time_below_prior_peak=float(underwater.mean()),
            longest_underwater_trading_days=int(episodes.trading_days.max())
            if len(episodes)
            else 0,
        )
        metric_map = {r["return_type"]: r for r in m.to_dict("records")}
        metric_map["benchmark"] = bm
        summary = dict(
            id=eid,
            **dict(zip(KEYS, key, strict=False)),
            label=LABELS[key[0]],
            academic=academic,
            start=dates[0],
            end=dates[-1],
            events=len(snapshots),
            securities=len(histories),
            metrics=metric_map,
        )
        write(
            OUT / "experiments" / f"{eid}.json",
            dict(
                **summary,
                dates=dates.strftime("%Y-%m-%d").tolist(),
                curves=curves,
                snapshots=snapshots,
                positions=histories,
            ),
        )
        catalog.append(summary)
        checks.append(
            dict(
                id=eid,
                fee_max_error=fee_error,
                borrow_max_error=borrow_error,
                events=len(snapshots),
                trades=len(ts),
            )
        )
        print(f"{number + 1}/180 {eid}: {len(snapshots)} snapshots reconciled", flush=True)
    write(
        OUT / "manifest.json",
        dict(
            schema=1,
            as_of="2026-08-28",
            initial_capital=10000000,
            experiments=catalog,
            securities=metadata,
            price_columns=[
                "date",
                "open",
                "high",
                "low",
                "close",
                "ema100",
                "supertrend",
                "supertrend_bullish",
            ],
        ),
    )
    write(
        ROOT / "reports/dashboard_validation.json",
        dict(experiments=len(catalog), securities=len(metadata), checks=checks),
    )
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(
        f"Complete: {len(catalog)} experiments; {size / 1e6:.1f} MB of lazy-loaded JSON", flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-prices", action="store_true")
    args = parser.parse_args()
    main(args.limit, args.skip_prices)
