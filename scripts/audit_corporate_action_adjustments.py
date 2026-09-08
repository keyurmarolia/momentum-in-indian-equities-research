"""Reconcile parsed split/bonus factors to observed raw-price discontinuities."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from momentum_india.config import PROJECT_ROOT


def main() -> None:
    processed = PROJECT_ROOT / "data" / "processed"
    market = pd.read_parquet(
        processed / "equity_market_panel.parquet",
        columns=["date", "symbol", "nse_symbol", "raw_close", "close", "share_multiplier_event"],
    ).sort_values(["symbol", "date"])
    market["previous_raw_close"] = market.groupby("symbol")["raw_close"].shift()
    events = market.loc[~market["share_multiplier_event"].eq(1.0)].copy()
    events["observed_raw_price_ratio"] = events["previous_raw_close"] / events["raw_close"]
    events["ratio_to_expected"] = (
        events["observed_raw_price_ratio"] / events["share_multiplier_event"]
    )
    events["absolute_log_error"] = np.log(events["ratio_to_expected"]).abs()
    events["within_25_percent_of_expected"] = events["ratio_to_expected"].between(0.75, 1.25)
    events.to_csv(processed / "corporate_action_price_reconciliation.csv", index=False)
    usable = events.dropna(subset=["ratio_to_expected"])
    audit = {
        "events_on_observed_trading_dates": len(events),
        "events_with_previous_raw_close": len(usable),
        "median_ratio_to_expected": float(usable["ratio_to_expected"].median()),
        "percent_within_25_percent": float(100 * usable["within_25_percent_of_expected"].mean()),
        "unreconciled_event_rows": int((~usable["within_25_percent_of_expected"]).sum()),
    }
    (processed / "corporate_action_price_reconciliation_summary.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(audit)
    if audit["percent_within_25_percent"] < 90:
        raise RuntimeError("Fewer than 90% of parsed share actions reconcile to raw-price moves")


if __name__ == "__main__":
    main()
