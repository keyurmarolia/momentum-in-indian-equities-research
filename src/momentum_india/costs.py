from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import PROJECT_ROOT


@lru_cache(maxsize=4)
def load_current_cost_schedule(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or PROJECT_ROOT / "config" / "current_cost_schedule.csv")


@lru_cache(maxsize=1)
def _current_cost_parameters() -> dict[str, float]:
    table = load_current_cost_schedule()

    def row(component: str, side: str | None = None) -> pd.Series:
        rows = table.loc[table["component"].eq(component)]
        if side is not None:
            rows = rows.loc[rows["side"].isin([side, "both"])]
        if len(rows) != 1:
            raise ValueError(f"Expected one {component}/{side} rule, found {len(rows)}")
        return rows.iloc[0]

    brokerage = row("brokerage")
    return {
        "brokerage_rate": float(brokerage.rate),
        "brokerage_cap": float(brokerage.cap_inr),
        "exchange": float(row("exchange_transaction").rate),
        "sebi": float(row("sebi_turnover").rate),
        "ipft": float(row("ipft").rate),
        "stamp_buy": float(row("stamp_duty", "buy").rate),
        "dp_sell": float(row("dp_charge", "sell").rate),
        "gst": float(row("gst").rate),
    }


@lru_cache(maxsize=1)
def _historical_stt():
    table = pd.read_csv(
        PROJECT_ROOT / "data/reference/trading_cost_history.csv",
        parse_dates=["effective_from", "effective_to"],
    )
    return tuple(table.loc[table.component.eq("STT")].itertuples(index=False))


@lru_cache(maxsize=8192)
def stt_rates_on(day):
    day = pd.Timestamp(day)
    rows = [
        r
        for r in _historical_stt()
        if r.effective_from <= day and (pd.isna(r.effective_to) or day <= r.effective_to)
    ]
    if len(rows) != 1:
        raise ValueError(f"No unique delivery STT rule for {day}")
    return rows[0].buy_rate / 100, rows[0].sell_rate / 100


def delivery_trade_cost(
    buy_value: float,
    sell_value: float,
    buy_orders: int = 1,
    sell_orders: int = 1,
    sold_isins: int = 0,
    buy_order_values: list[float] | None = None,
    sell_order_values: list[float] | None = None,
    schedule: pd.DataFrame | None = None,
    trade_date: pd.Timestamp | None = None,
) -> dict[str, float]:
    """Component bridge for the dated current-cost backcast."""
    table = schedule if schedule is not None else load_current_cost_schedule()
    turnover = buy_value + sell_value

    def one(component: str, side: str | None = None) -> pd.Series:
        cached = table.attrs.setdefault("_component_rows", {})
        if (component, side) in cached:
            return cached[(component, side)]
        rows = table.loc[table["component"].eq(component)]
        if side is not None:
            rows = rows.loc[rows["side"].isin([side, "both"])]
        if len(rows) != 1:
            raise ValueError(f"Expected one {component}/{side} rule, found {len(rows)}")
        cached[(component, side)] = rows.iloc[0]
        return cached[(component, side)]

    broker = one("brokerage")
    if buy_order_values is None:
        buy_order_values = [buy_value / buy_orders] * buy_orders if buy_orders else []
    if sell_order_values is None:
        sell_order_values = [sell_value / sell_orders] * sell_orders if sell_orders else []
    if (
        abs(sum(buy_order_values) - buy_value) > 0.01
        or abs(sum(sell_order_values) - sell_value) > 0.01
    ):
        raise ValueError("Order-level values must reconcile to side turnover")
    brokerage = sum(min(value * broker.rate, broker.cap_inr) for value in buy_order_values)
    brokerage += sum(min(value * broker.rate, broker.cap_inr) for value in sell_order_values)
    buy_stt, sell_stt = (
        stt_rates_on(trade_date)
        if trade_date is not None
        else (one("stt", "buy").rate, one("stt", "sell").rate)
    )
    stt = buy_value * buy_stt + sell_value * sell_stt
    exchange = turnover * one("exchange_transaction").rate
    sebi = turnover * one("sebi_turnover").rate
    ipft = turnover * one("ipft").rate
    stamp = buy_value * one("stamp_duty", "buy").rate
    dp = sold_isins * one("dp_charge", "sell").rate
    gst_base = brokerage + exchange + sebi + ipft + dp
    gst = gst_base * one("gst").rate
    components = {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_transaction": exchange,
        "sebi_turnover": sebi,
        "ipft": ipft,
        "stamp_duty": stamp,
        "dp_charge": dp,
        "gst": gst,
    }
    components["total"] = sum(components.values())
    return components


def delivery_order_costs(
    order_values: pd.Series,
    sides: pd.Series,
    trade_date: pd.Timestamp,
    schedule: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return the cost allocation for each executed delivery order.

    Each row represents one security-side executed order. Percentage levies
    are applied to that order's value, brokerage is capped per order, and the
    demat debit fee is charged once for every security sold that day.
    """
    values = pd.to_numeric(order_values, errors="raise").astype(float)
    directions = sides.astype(str).str.lower()
    if not directions.isin(["buy", "sell"]).all():
        raise ValueError("Order sides must be buy or sell")
    if values.lt(0).any():
        raise ValueError("Order values must be non-negative")
    table = schedule if schedule is not None else load_current_cost_schedule()

    def one(component: str, side: str | None = None) -> pd.Series:
        rows = table.loc[table["component"].eq(component)]
        if side is not None:
            rows = rows.loc[rows["side"].isin([side, "both"])]
        if len(rows) != 1:
            raise ValueError(f"Expected one {component}/{side} rule, found {len(rows)}")
        return rows.iloc[0]

    result = pd.DataFrame(index=values.index)
    if schedule is None:
        parameters = _current_cost_parameters()
        brokerage_rate = parameters["brokerage_rate"]
        brokerage_cap = parameters["brokerage_cap"]
        exchange_rate = parameters["exchange"]
        sebi_rate = parameters["sebi"]
        ipft_rate = parameters["ipft"]
        stamp_rate = parameters["stamp_buy"]
        gst_rate = parameters["gst"]
        dp_rate = parameters["dp_sell"]
    else:
        broker = one("brokerage")
        brokerage_rate = float(broker.rate)
        brokerage_cap = float(broker.cap_inr)
        exchange_rate = float(one("exchange_transaction").rate)
        sebi_rate = float(one("sebi_turnover").rate)
        ipft_rate = float(one("ipft").rate)
        stamp_rate = float(one("stamp_duty", "buy").rate)
        gst_rate = float(one("gst").rate)
        dp_rate = float(one("dp_charge", "sell").rate)
    result["brokerage"] = values.mul(brokerage_rate).clip(upper=brokerage_cap)
    buy_stt, sell_stt = stt_rates_on(trade_date)
    result["stt"] = values * directions.map({"buy": buy_stt, "sell": sell_stt})
    result["exchange_transaction"] = values * exchange_rate
    result["sebi_turnover"] = values * sebi_rate
    result["ipft"] = values * ipft_rate
    result["stamp_duty"] = values.where(directions.eq("buy"), 0.0) * stamp_rate
    result["dp_charge"] = directions.eq("sell").astype(float) * dp_rate
    taxable = (
        result["brokerage"]
        + result["exchange_transaction"]
        + result["sebi_turnover"]
        + result["ipft"]
        + result["dp_charge"]
    )
    result["gst"] = taxable * gst_rate
    result["total"] = result.sum(axis=1)
    return result


def delivery_buy_total_cost(
    order_values: list[float], trade_date: pd.Timestamp, scale: float = 1.0
) -> float:
    """Fast scalar cost for sizing a batch of delivery purchases."""
    parameters = _current_cost_parameters()
    values = [max(float(value) * float(scale), 0.0) for value in order_values]
    brokerage = sum(
        min(value * parameters["brokerage_rate"], parameters["brokerage_cap"]) for value in values
    )
    turnover = sum(values)
    buy_stt, _ = stt_rates_on(trade_date)
    exchange = turnover * parameters["exchange"]
    sebi = turnover * parameters["sebi"]
    ipft = turnover * parameters["ipft"]
    stamp = turnover * parameters["stamp_buy"]
    gst = (brokerage + exchange + sebi + ipft) * parameters["gst"]
    return brokerage + turnover * buy_stt + exchange + sebi + ipft + stamp + gst
