"""Validate and promote the official NSE main-board daily equity panel."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import yaml

from momentum_india.config import PROJECT_ROOT
from momentum_india.corporate_actions import adjust_prices_for_share_actions
from momentum_india.universe import validate_market_schema


def main() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    interim = PROJECT_ROOT / "data" / "interim"
    bulk_dir = interim / "nse_mainboard_equity_by_year"
    annual_paths = sorted(bulk_dir.glob("nse_mainboard_equity_*.parquet"))
    if not annual_paths:
        raise RuntimeError("Official NSE annual equity files are unavailable")
    frame = pd.concat((pd.read_parquet(path) for path in annual_paths), ignore_index=True)
    frame["history_source"] = "nse_official_daily_bhavcopy"
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    if "isin" in frame.columns:
        frame["isin"] = frame["isin"].astype("string").str.strip()
        frame.loc[~frame["isin"].str.startswith("INE", na=False), "isin"] = pd.NA
        # Early legacy bhavcopies predate the ISIN column. Backfill only when
        # all official references agree on one equity ISIN for the symbol.
        reference_pairs: list[pd.DataFrame] = [frame[["nse_symbol", "isin"]].dropna()]
        current_master = PROJECT_ROOT / "data" / "reference" / "current_fyers_equity_master.csv"
        delisted_register = PROJECT_ROOT / "data" / "reference" / "nse_delisted_since_2000.csv"
        action_raw = (
            PROJECT_ROOT / "data" / "raw" / "reference" / "nse_corporate_actions_2000_2026.json"
        )
        if current_master.exists():
            reference_pairs.append(pd.read_csv(current_master, usecols=["nse_symbol", "isin"]))
        if delisted_register.exists():
            reference_pairs.append(pd.read_csv(delisted_register, usecols=["nse_symbol", "isin"]))
        if action_raw.exists():
            action_identity = pd.DataFrame(json.loads(action_raw.read_text(encoding="utf-8")))
            reference_pairs.append(
                action_identity[["symbol", "isin"]].rename(columns={"symbol": "nse_symbol"})
            )
        identities = pd.concat(reference_pairs, ignore_index=True).dropna()
        identities["isin"] = identities["isin"].astype("string").str.strip()
        identities = identities.loc[identities["isin"].str.startswith("INE", na=False)]
        unique = identities.groupby("nse_symbol")["isin"].agg(lambda values: sorted(set(values)))
        unambiguous = unique.loc[unique.str.len().eq(1)].str[0]
        frame["isin"] = frame["isin"].fillna(frame["nse_symbol"].map(unambiguous))
    frame = frame.sort_values(["date", "symbol", "history_source"])
    frame = frame.drop_duplicates(["date", "symbol"], keep="first")
    numeric = ["open", "high", "low", "close", "volume"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume"])
    frame = frame.loc[
        (frame[["open", "high", "low", "close"]] > 0).all(axis=1) & frame["volume"].ge(0)
    ]
    # Two legacy NSE rows report a close marginally outside the published
    # high-low envelope. Preserve every raw field, but repair the analytical
    # envelope so range-based indicators remain internally valid.
    for column in ("open", "high", "low", "close"):
        frame[f"raw_{column}"] = frame[column]
    frame["ohlc_envelope_repaired"] = frame["high"].lt(
        frame[["open", "close"]].max(axis=1)
    ) | frame["low"].gt(frame[["open", "close"]].min(axis=1))
    frame["high"] = frame[["high", "open", "close"]].max(axis=1)
    frame["low"] = frame[["low", "open", "close"]].min(axis=1)
    action_path = PROJECT_ROOT / "data" / "reference" / "nse_share_action_factors.csv"
    if not action_path.exists():
        raise RuntimeError("Build the official NSE split/bonus factor table before panel promotion")
    actions = pd.read_csv(action_path, parse_dates=["ex_date"])
    frame = adjust_prices_for_share_actions(frame, actions)
    validate_market_schema(frame)

    frame["daily_return"] = frame.groupby("symbol")["close"].pct_change(fill_method=None)
    threshold = float(config["universe"]["unresolved_price_jump_threshold"])
    frame["unresolved_price_jump"] = frame["daily_return"].abs().gt(threshold)
    calculated_traded_value = frame["raw_close"] * frame["volume"]
    if "official_traded_value_inr" in frame.columns:
        official = pd.to_numeric(frame["official_traded_value_inr"], errors="coerce")
        frame["daily_traded_value"] = official.where(official.ge(0), calculated_traded_value)
    else:
        frame["daily_traded_value"] = calculated_traded_value
    coverage = (
        frame.groupby("symbol")
        .agg(
            observations=("date", "size"),
            first_date=("date", "min"),
            last_date=("date", "max"),
            unresolved_price_jumps=("unresolved_price_jump", "sum"),
            median_daily_traded_value_inr=("daily_traded_value", "median"),
            history_source=("history_source", "first"),
        )
        .reset_index()
    )
    coverage["eligible_252_days"] = coverage["observations"].ge(252)
    coverage["quality_status"] = np.where(
        coverage["unresolved_price_jumps"].gt(0), "review_price_jumps", "pass"
    )
    processed = PROJECT_ROOT / "data" / "processed"
    frame.to_parquet(processed / "equity_market_panel.parquet", index=False)
    coverage.to_csv(processed / "equity_market_coverage.csv", index=False)
    membership = frame[["date", "symbol", "nse_symbol", "isin"]].copy()
    membership["month"] = membership["date"].dt.to_period("M").astype(str)
    last_market_day = membership.groupby("month")["date"].transform("max")
    membership = membership.loc[membership["date"].eq(last_market_day)].drop_duplicates(
        ["month", "symbol"]
    )
    membership["membership_definition"] = "traded_EQ_on_last_exchange_day_of_month"
    membership.to_parquet(processed / "nse_monthly_traded_membership.parquet", index=False)
    identity = (
        frame.groupby(["nse_symbol", "isin"], dropna=False)
        .agg(
            first_traded_date=("date", "min"),
            last_traded_date=("date", "max"),
            observations=("date", "size"),
        )
        .reset_index()
    )
    identity.to_csv(processed / "nse_symbol_isin_history.csv", index=False)
    print(
        f"Complete: {len(frame):,} rows, {frame.symbol.nunique():,} symbols, "
        f"{coverage.eligible_252_days.sum():,} with at least 252 observations"
    )


if __name__ == "__main__":
    main()
