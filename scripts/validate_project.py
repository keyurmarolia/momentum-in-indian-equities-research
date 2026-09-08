"""Validate the research grid, executed figures, links and return identities."""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]


def main():
    errors = []
    figures = 0
    observations = 0
    widgets = 0
    cfg = yaml.safe_load((ROOT / "config/config.yaml").read_text())
    assert cfg["formation"]["periods"] == ["6M", "12M"]
    assert cfg["rebalancing"]["frequencies"] == ["1M", "3M", "6M"]
    assert cfg["concentration"]["holdings"] == [12, 24, 50]
    assert cfg["portfolio"]["maintenance_modes"] == ["equal_weight", "winner_drift"]
    assert cfg["universe"]["capacity"]["reference_aum_inr"] == 10_000_000
    assert cfg["universe"]["capacity"]["maximum_mdtv_participation"] == 0.05
    assert cfg["rebalancing"]["model_multi_day_execution"] is False
    km = cfg["strategies"]["km_momentum"]
    assert (
        km["ema_length"],
        km["minimum_close_above_ema"],
        km["supertrend_length"],
        km["supertrend_multiplier"],
    ) == (100, 0.03, 10, 3.0)
    books = sorted((ROOT / "notebooks").glob("*.ipynb"))
    if len(books) != 23 or [int(p.name[:2]) for p in books] != list(range(23)):
        errors.append("Notebook numbering is not exactly 00–22")
    for p in books:
        b = json.loads(p.read_text())
        equity_charts = 0
        heatmaps = 0
        for i, cell in enumerate(b["cells"]):
            if cell["cell_type"] != "code":
                continue
            if cell.get("execution_count") is None:
                errors.append(f"{p.name}: cell {i} unexecuted")
            outs = cell.get("outputs", [])
            has_plot = False
            text = ""
            for out in outs:
                if out["output_type"] == "error":
                    errors.append(f"{p.name}: execution error")
                data = out.get("data", {})
                widgets += int("application/vnd.jupyter.widget-view+json" in data)
                text += "".join(data.get("text/html", []))
                fig = data.get("application/vnd.plotly.v1+json")
                if not fig:
                    continue
                figures += 1
                has_plot = True
                layout = fig["layout"]
                if not layout.get("title", {}).get("text"):
                    errors.append(f"{p.name}: chart missing title")
                if layout.get("margin", {}).get("t", 0) < 80:
                    errors.append(f"{p.name}: title margin too small")
                if layout.get("yaxis", {}).get("type") == "log" and layout.get("xaxis", {}).get(
                    "rangeslider", {}
                ).get("visible"):
                    equity_charts += 1
                for trace in fig.get("data", []):
                    if trace["type"] == "heatmap":
                        heatmaps += 1
                        expected = (6, 5) if p.name.startswith("22_") else (3, 3)
                        if (len(trace["x"]), len(trace["y"])) != expected:
                            errors.append(f"{p.name}: incorrect heatmap grid")
                        if trace.get("texttemplate") != "%{text}":
                            errors.append(f"{p.name}: missing heatmap values")
            observations += text.count("Observation.")
            if has_plot and "Observation." not in text:
                errors.append(f"{p.name}: chart cell {i} has no observation")
        if 2 <= int(p.name[:2]) <= 21:
            if equity_charts < 4 or heatmaps != 4:
                errors.append(f"{p.name}: missing equity/regime paths or risk heatmaps")
        h = ROOT / "reports/html" / (p.stem + ".html")
        if not h.exists():
            errors.append(f"{p.name}: HTML missing")
        else:
            body = h.read_text()
            for href in re.findall(r'href="([^"]+)"', body):
                if href.startswith("../tables/") or (
                    href.endswith(".html") and not href.startswith(("http", "/"))
                ):
                    if not (h.parent / href).resolve().exists():
                        errors.append(f"{p.name}: broken link {href}")
    if widgets:
        errors.append(f"{widgets} unsupported widget outputs")
    if figures < 180:
        errors.append(f"Too few executed figures: {figures}")
    for p in (ROOT / "data/tax_rules").glob("*.csv"):
        t = pd.read_csv(p)
        if not {"effective_from", "effective_to", "source_url", "validation_status"} <= set(t):
            errors.append(f"{p.name}: missing provenance")
        elif t.source_url.isna().any():
            errors.append(f"{p.name}: missing source")
    m = pd.read_csv(ROOT / "data/processed/backtest_metrics.csv")
    if len(m) != 576 or m.duplicated(KEYS + ["return_type"]).any():
        errors.append("Metric grid is incomplete or duplicated")
    if "panel" in m:
        errors.append("Obsolete experiment dimension present")
    long = m[m.strategy != "jt_academic"].pivot(
        index=KEYS, columns="return_type", values="ending_wealth_multiple"
    )
    if not (long.gross <= long.raw + 1e-9).all():
        errors.append("After-cost wealth exceeds raw")
    if not (long.post_tax <= long.gross + 1e-9).all():
        errors.append("Post-tax wealth exceeds after-cost")
    daily_columns = KEYS + [
        "return_type",
        "date",
        "return",
        "equity",
        "cash_value",
        "transaction_cost",
        "tax_paid",
        "cost_brokerage",
        "cost_stt",
        "cost_exchange_transaction",
        "cost_sebi_turnover",
        "cost_ipft",
        "cost_stamp_duty",
        "cost_dp_charge",
        "cost_gst",
    ]
    daily = pd.read_parquet(ROOT / "data/processed/backtest_daily.parquet", columns=daily_columns)
    summary = m.set_index(KEYS + ["return_type"])
    for key, g in daily.groupby(KEYS + ["return_type"]):
        g = g.sort_values("date")
        growth = (1 + g["return"]).cumprod().to_numpy()
        if not np.allclose(g.equity.to_numpy() / 10_000_000, growth, rtol=1e-8, atol=1e-8):
            errors.append(f"Wealth identity failed: {key}")
        if not np.isclose(growth[-1], summary.loc[key, "ending_wealth_multiple"]):
            errors.append(f"Metric wealth mismatch: {key}")
    holdings = pd.read_parquet(ROOT / "data/processed/portfolio_holdings_at_rebalance.parquet")
    if holdings.weight.isna().any():
        errors.append("Missing actual portfolio weights")
    selected = holdings[(holdings.strategy == "km_momentum") & holdings.target_selected]
    if not selected.km_entry_eligible.all():
        errors.append("KM selected ineligible stocks")
    if not selected.supertrend_bullish.all():
        errors.append("KM selected bearish Supertrend")
    max_weights = holdings[(holdings.strategy != "jt_academic") & holdings.target_selected]
    cap = np.where(max_weights.maintenance == "winner_drift", 2, 1) / max_weights.holdings_n
    if (
        max_weights.target_weight.isna().any()
        or not (max_weights.target_weight <= cap + 1e-8).all()
    ):
        errors.append("Scheduled target-position cap exceeded")

    trades = pd.read_parquet(ROOT / "data/processed/trade_ledger.parquet")
    market = pd.read_parquet(
        ROOT / "data/processed/equity_market_panel.parquet",
        columns=["date", "symbol", "open", "close"],
    )
    executed = trades.loc[~trades.exit_reason.eq("confirmed_delisting_zero_recovery")]
    opens = market.set_index(["date", "symbol"])["open"]
    # Validate actual filled weights, not merely the nominal selection slots.
    events = pd.read_csv(
        ROOT / "data/processed/rebalance_diagnostics.csv", parse_dates=["execution_date"]
    )
    actual = max_weights.merge(
        events[KEYS + ["execution_date", "equity_before_rebalance", "transaction_cost"]],
        on=KEYS + ["execution_date"],
        validate="many_to_one",
    )
    fillable = (
        opens.reindex(pd.MultiIndex.from_arrays([actual.execution_date, actual.symbol]))
        .notna()
        .to_numpy()
    )
    target_cap = np.where(actual.maintenance.eq("winner_drift"), 2, 1) / actual.holdings_n
    cost_adjusted_cap = target_cap / (1 - actual.transaction_cost / actual.equity_before_rebalance)
    if (actual.weight.gt(cost_adjusted_cap + 1e-8) & fillable).any():
        errors.append("Executable actual holding exceeds its fee-adjusted position cap")
    matched = opens.reindex(pd.MultiIndex.from_frame(executed[["date", "symbol"]])).to_numpy()
    if pd.isna(matched).any() or not np.allclose(
        matched, executed.price.to_numpy(), rtol=0, atol=1e-10
    ):
        errors.append("An executed trade does not match an actual observed opening price")
    zero = trades.loc[trades.price.eq(0)]
    if not zero.exit_reason.eq("confirmed_delisting_zero_recovery").all():
        errors.append("A zero-price transaction is not a confirmed-delisting write-down")
    gross = daily.loc[daily.return_type.eq("gross")]
    components = [
        "cost_brokerage",
        "cost_stt",
        "cost_exchange_transaction",
        "cost_sebi_turnover",
        "cost_ipft",
        "cost_stamp_duty",
        "cost_dp_charge",
        "cost_gst",
    ]
    if not np.allclose(
        gross.transaction_cost, gross[components].sum(axis=1), rtol=1e-10, atol=1e-7
    ):
        errors.append("Daily transaction-cost components do not reconcile")
    if gross.cash_value.lt(-0.01).any():
        errors.append("Long-only after-cost cash is negative")
    tax = pd.read_csv(ROOT / "data/processed/annual_tax_ledger.csv")
    paid = daily.loc[daily.return_type.eq("post_tax"), "tax_paid"].sum()
    if not np.isclose(paid, tax.total_tax.sum(), rtol=1e-10, atol=0.01):
        errors.append("Annual tax ledger does not reconcile to post-tax wealth deductions")
    if errors:
        print("VALIDATION FAILED\n" + "\n".join(errors))
        return 1
    print(
        f"VALIDATION PASSED: {len(books)} notebooks, {figures} interactive figures, {observations} observations, zero widgets; 576 wealth paths and grid identities reconciled."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
