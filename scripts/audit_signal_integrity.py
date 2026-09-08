"""Independently reconcile saved rankings and all scheduled memberships."""

import json

import numpy as np
import pandas as pd

from momentum_india.config import PROJECT_ROOT

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance", "signal_date"]


def main():
    p = PROJECT_ROOT / "data/processed"
    ranks = pd.read_parquet(p / "signal_rankings_monthly.parquet")
    market = pd.read_parquet(
        p / "equity_market_panel.parquet", columns=["date", "symbol", "close", "open"]
    )
    close = market.set_index(["date", "symbol"]).close
    first = close.reindex(
        pd.MultiIndex.from_arrays([ranks.formation_start_date, ranks.symbol])
    ).to_numpy()
    last = close.reindex(pd.MultiIndex.from_arrays([ranks.signal_date, ranks.symbol])).to_numpy()
    assert np.allclose(last / first - 1, ranks.raw_momentum, atol=1e-12)
    opens = market.set_index(["date", "symbol"]).open
    unavailable = (
        opens.reindex(pd.MultiIndex.from_arrays([ranks.execution_date, ranks.symbol])).isna().sum()
    )
    assert (ranks.signal_date < ranks.execution_date).all()
    assert not ranks.duplicated(["formation_period", "signal_date", "symbol"]).any()
    cross = dict(tuple(ranks.groupby(["formation_period", "signal_date"])))
    targets = pd.read_parquet(p / "portfolio_targets.parquet")
    selected = dict(tuple(targets.groupby(KEYS)))
    events = pd.read_csv(
        p / "portfolio_rebalance_events.csv", parse_dates=["signal_date", "execution_date"]
    )
    assert not events.duplicated(KEYS).any()
    columns = dict(
        raw_momentum="raw_momentum",
        vol_adjusted="vol_adjusted",
        jensen_alpha="jensen_alpha",
        km_momentum="raw_momentum",
        jt_academic="raw_momentum",
    )
    for row in events.itertuples():
        score = columns[row.strategy]
        pool = cross[(row.formation_period, row.signal_date)].dropna(subset=[score])
        if row.strategy == "km_momentum":
            assert (
                pool.km_entry_eligible
                == (
                    pool.supertrend_bullish
                    & pool.ema100.mul(1.03).le(
                        pd.Series(last, index=ranks.index).reindex(pool.index)
                    )
                )
            ).all()
            pool = pool.loc[pool.km_entry_eligible]
        ordered = pool.sort_values([score, "symbol"], ascending=[False, True])
        if row.strategy == "jt_academic":
            half = min(row.holdings_n // 2, len(ordered) // 2)
            expected = {
                **dict.fromkeys(ordered.head(half).symbol, 1 / row.holdings_n),
                **dict.fromkeys(ordered.tail(half).symbol, -1 / row.holdings_n),
            }
        else:
            expected = dict.fromkeys(ordered.head(row.holdings_n).symbol, 1 / row.holdings_n)
        key = tuple(getattr(row, k) for k in KEYS)
        actual = selected.get(key, targets.iloc[:0])
        assert not actual.symbol.duplicated().any(), key
        assert set(actual.symbol) == set(expected), key
        assert np.allclose(actual.weight, actual.symbol.map(expected)), key
    benchmark = (
        pd.read_csv(p / "nifty50_price_index.csv", parse_dates=["date"]).set_index("date").close
    )
    nav = (
        pd.read_csv(p / "absl_liquid_fund_continuous.csv", parse_dates=["date"])
        .set_index("date")
        .continuous_nav
    )
    calendar = benchmark.index.intersection(market.date.unique()).sort_values()
    # Independent as-of alignment, including published non-trading-day NAVs.
    reference = (
        nav.reindex(nav.index.union(calendar))
        .sort_index()
        .ffill()
        .reindex(calendar)
        .pct_change(fill_method=None)
    )
    bm = benchmark.reindex(calendar).pct_change(fill_method=None)
    panel = market.pivot(index="date", columns="symbol", values="close").reindex(calendar)
    # Deterministic coverage of both lookbacks, early/late dates and symbols.
    sample = ranks.iloc[np.linspace(0, len(ranks) - 1, 60, dtype=int)]
    for row in sample.itertuples():
        window = panel.loc[row.formation_start_date : row.signal_date, row.symbol].ffill()
        log_vol = np.log(window).diff().iloc[1:].std() * np.sqrt(252)
        assert np.isclose(row.vol_adjusted, row.raw_momentum / log_vol, atol=1e-10)
        returns = window.pct_change(fill_method=None).iloc[1:]
        y = returns - reference.reindex(returns.index)
        x = bm.reindex(returns.index) - reference.reindex(returns.index)
        valid = x.notna() & y.notna()
        intercept = np.linalg.lstsq(
            np.column_stack([np.ones(valid.sum()), x[valid]]), y[valid], rcond=None
        )[0][0]
        assert np.isclose(row.jensen_alpha, intercept, atol=1e-10)
    result = dict(
        raw_scores_reconciled=len(ranks),
        independent_ols_and_volatility_checks=len(sample),
        scheduled_memberships_reconciled=len(events),
        ranking_rows_without_next_open=int(unavailable),
    )
    (PROJECT_ROOT / "reports/signal_integrity.json").write_text(json.dumps(result, indent=2))
    print(result)


if __name__ == "__main__":
    main()
