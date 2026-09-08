"""Cache-first FYERS download of the Nifty 50 price-index benchmark."""

from __future__ import annotations

import os

import pandas as pd
import yaml
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

from momentum_india.config import PROJECT_ROOT
from momentum_india.data.fyers_client import (
    FyersHistoryClient,
    RequestBudget,
    daily_history_windows,
)

SYMBOL = "NSE:NIFTY50-INDEX"
COLUMNS = ["epoch", "open", "high", "low", "close", "volume"]


def main() -> None:
    settings = yaml.safe_load(
        (PROJECT_ROOT / "config" / "data_acquisition.yaml").read_text(encoding="utf-8")
    )["equity_history"]
    start = pd.Timestamp(settings["candidate_start"]).date()
    end = pd.Timestamp(settings["end"]).date()
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.environ.get("FYERS_ACCESS_TOKEN")
    client_id = os.environ.get("FYERS_CLIENT_ID")
    if not token or not client_id:
        raise RuntimeError("FYERS credentials are missing from the local .env")
    cache = PROJECT_ROOT / "data" / "raw" / "fyers_history_cache"
    sdk = fyersModel.FyersModel(client_id=client_id, token=token, is_async=False, log_level="ERROR")
    budget = RequestBudget(
        max_per_second=2,
        max_per_minute=100,
        max_per_day=int(settings["maximum_fyers_calls_per_run"]),
        minimum_interval_seconds=float(settings["minimum_interval_seconds"]),
        ledger_path=cache / "request_ledger.json",
    )
    client = FyersHistoryClient(sdk.history, cache, budget=budget, max_retries=1)
    frames = []
    windows = list(daily_history_windows(start, end))
    print(f"Preflight: {len(windows)} maximum benchmark requests; cache checked before every call")
    for left, right in windows:
        response = client.history(
            {
                "symbol": SYMBOL,
                "resolution": "D",
                "date_format": "1",
                "range_from": left.isoformat(),
                "range_to": right.isoformat(),
                "cont_flag": "0",
            }
        )
        if response.get("candles"):
            frames.append(pd.DataFrame(response["candles"], columns=COLUMNS))
    if not frames:
        raise RuntimeError("No Nifty 50 benchmark rows acquired")
    output = pd.concat(frames, ignore_index=True)
    output["date"] = (
        pd.to_datetime(output["epoch"], unit="s", utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    output = output.drop(columns="epoch").drop_duplicates("date").sort_values("date")
    output["symbol"] = SYMBOL
    target = PROJECT_ROOT / "data" / "processed" / "nifty50_price_index.csv"
    output[["date", "symbol", "open", "high", "low", "close", "volume"]].to_csv(target, index=False)
    print(
        f"Complete: {len(output):,} observations from {output.date.min().date()} to {output.date.max().date()}"
    )


if __name__ == "__main__":
    main()
