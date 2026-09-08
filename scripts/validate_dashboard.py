"""Reconcile the exported static dashboard with the canonical backtests."""

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from momentum_india.dashboard_data import KEYS
from momentum_india.risk import align_cash_nav

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard/public/data"


def main():
    manifest = json.loads((DATA / "manifest.json").read_text())
    assert len(manifest["experiments"]) == 180
    assert len({e["id"] for e in manifest["experiments"]}) == 180
    frame = pd.read_parquet(
        ROOT / "data/processed/backtest_daily.parquet",
        columns=KEYS
        + ["return_type", "date", "equity", "cash_value", "transaction_cost", "borrow_cost"],
        filters=[("return_type", "in", ["gross", "academic_borrow_6pct"])],
    )
    daily = {key: g.sort_values("date").set_index("date") for key, g in frame.groupby(KEYS)}
    nav = (
        pd.read_csv(ROOT / "data/processed/absl_liquid_fund_continuous.csv", parse_dates=["date"])
        .set_index("date")
        .continuous_nav
    )
    max_error = 0
    snapshot_count = 0
    episode_count = 0
    fill_count = 0
    cash_events = 0
    max_fee_error = 0
    for i, summary in enumerate(manifest["experiments"]):
        path = DATA / "experiments" / f"{summary['id']}.json.gz"
        export = json.loads(gzip.decompress(path.read_bytes()))
        source = daily[tuple(summary[k] for k in KEYS)]
        layer = "academic_borrow_6pct" if summary["academic"] else "gross"
        assert export["dates"] == source.index.strftime("%Y-%m-%d").tolist()
        assert np.allclose(export["curves"][layer], source.equity / 1e7, atol=1e-8, rtol=0)
        assert all(len(v) == len(source) for v in export["curves"].values())
        assert len(export["snapshots"]) == {"1M": 232, "3M": 77, "6M": 39}[summary["frequency"]]
        for snapshot in export["snapshots"]:
            snapshot_count += 1
            cash_events += not bool(snapshot["holdings"])
            assert (
                abs(
                    sum(h["value"] for h in snapshot["holdings"])
                    + snapshot["cash"]
                    - snapshot["capital"]
                )
                < 0.001
            )
            assert len({h["id"] for h in snapshot["holdings"]}) == len(snapshot["holdings"])
        stock_profit = 0
        fees = 0
        borrow = 0
        for sid, position in export["positions"].items():
            assert (DATA / "stocks" / f"{sid}.json.gz").exists()
            assert sid in manifest["securities"]
            fees += sum(t["fee"] for t in position["trades"])
            stock_profit += sum(e["net_pnl"] for e in position["episodes"])
            borrow += sum(e["borrow"] for e in position["episodes"])
            episode_count += len(position["episodes"])
            fill_count += len(position["trades"])
            for e in position["episodes"]:
                assert abs(e["pnl"] - e["realized"] - e["unrealized"]) < 0.001
                assert abs(e["net_pnl"] - e["pnl"] + e["borrow"]) < 0.001
                assert e["exit"] is None or abs(e["quantity"]) < 1e-8
        cash_rates = align_cash_nav(nav, source.index).pct_change(fill_method=None).fillna(0)
        cash_income = float((source.cash_value.shift(1).fillna(0) * cash_rates).sum())
        expected = float(source.equity.iloc[-1] - 1e7)
        error = abs(stock_profit + cash_income - expected)
        assert error < max(0.05, abs(expected) * 1e-8), (summary["id"], error)
        max_error = max(max_error, error)
        fee_error = abs(fees - source.transaction_cost.sum())
        assert fee_error < 0.01, (summary["id"], fee_error)
        assert abs(borrow - source.borrow_cost.sum()) < 0.05
        max_fee_error = max(max_fee_error, fee_error)
        if (i + 1) % 30 == 0:
            print(f"{i + 1}/180 validated", flush=True)
    result = dict(
        experiments=180,
        securities=len(manifest["securities"]),
        scheduled_snapshots=snapshot_count,
        cash_only_snapshots=cash_events,
        position_episodes=episode_count,
        trade_legs=fill_count,
        maximum_total_profit_reconciliation_error_inr=max_error,
        maximum_total_fee_error_inr=max_fee_error,
        note="Stock net profit plus liquid-cash income equals canonical portfolio ending equity minus initial capital.",
    )
    (ROOT / "reports/dashboard_accounting_validation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
