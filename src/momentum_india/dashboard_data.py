"""Read-only presentation accounting for the research dashboard."""

from __future__ import annotations

import math
from collections import deque

import numpy as np
import pandas as pd

from .costs import load_current_cost_schedule, stt_rates_on

KEYS = ["strategy", "formation_period", "frequency", "holdings_n", "maintenance"]


def allocate_trade_fees(trades: pd.DataFrame) -> pd.Series:
    """Same per-order fee formula as the simulator, without rounding to paise."""
    s = load_current_cost_schedule().set_index("component")
    v = trades.trade_value.abs().to_numpy()
    buy = trades.trade_value.to_numpy() > 1e-9
    sell = trades.trade_value.to_numpy() < -1e-9
    active = buy | sell
    dates = pd.to_datetime(trades.date)
    rates = {day: stt_rates_on(day) for day in dates.unique()}
    br = dates.map(lambda d: rates[d][0]).to_numpy()
    sr = dates.map(lambda d: rates[d][1]).to_numpy()
    brokerage = np.minimum(v * s.loc["brokerage", "rate"], s.loc["brokerage", "cap_inr"]) * active
    exchange = v * s.loc["exchange_transaction", "rate"]
    sebi = v * s.loc["sebi_turnover", "rate"]
    ipft = v * s.loc["ipft", "rate"]
    dp = sell * s.loc["dp_charge", "rate"]
    stamp = v * buy * s.loc["stamp_duty", "rate"]
    stt = v * np.where(buy, br, sr)
    result = brokerage + exchange + sebi + ipft + dp + stamp + stt
    result += (brokerage + exchange + sebi + ipft + dp) * s.loc["gst", "rate"]
    return pd.Series(result * active, index=trades.index)


def position_history(trades: list[dict], last_price: float, last_date: str) -> dict:
    """FIFO lots and zero-to-zero episodes. Reversals close, then open a new leg.

    Position result includes trading fees but not portfolio tax or cash interest.
    Academic borrowing is attached separately by the exporter.
    """
    quantity = 0.0
    episodes, transactions = [], []
    lots = deque()
    current = None
    for trade in trades:
        delta, price, fee = (
            float(trade["quantity_change"]),
            float(trade["price"]),
            float(trade.get("fee", 0)),
        )
        before = quantity
        after = before + delta
        tolerance = max(1e-8, abs(before) * 1e-10)
        if abs(after) < tolerance:
            delta, after = -before, 0.0
        if before * after < 0:
            parts = [-before, after]
        else:
            parts = [delta]
        original = sum(abs(p) for p in parts)
        for change in parts:
            if abs(change) < 1e-12:
                continue
            part_fee = fee * abs(change) / original if original else 0.0
            opening = abs(quantity) < 1e-8
            if opening:
                quantity = 0.0
                current = dict(
                    id=len(episodes),
                    entry=trade["date"],
                    exit=None,
                    first_price=price,
                    last_price=price,
                    direction=1 if change > 0 else -1,
                    cash_flow=0.0,
                    fees=0.0,
                    realized=0.0,
                    matched_cost=0.0,
                    borrow=0.0,
                    trade_count=0,
                )
                episodes.append(current)
            adding = opening or quantity * change > 0
            if adding:
                lots.append([abs(change), price, part_fee / abs(change)])
                kind = "entry" if opening else "add"
            else:
                remaining = abs(change)
                close_fee_per_unit = part_fee / remaining
                while remaining > 1e-8 and lots:
                    lot = lots[0]
                    amount = min(remaining, lot[0])
                    current["realized"] += amount * (
                        current["direction"] * (price - lot[1]) - lot[2] - close_fee_per_unit
                    )
                    current["matched_cost"] += amount * (lot[1] + lot[2])
                    lot[0] -= amount
                    remaining -= amount
                    if lot[0] < 1e-8:
                        lots.popleft()
                if remaining > max(1e-7, abs(change) * 1e-9):
                    raise ValueError("Exit exceeds FIFO lots")
                kind = "exit" if abs(quantity + change) < tolerance else "trim"
            quantity += change
            if abs(quantity) < tolerance:
                quantity = 0.0
            current["cash_flow"] -= change * price
            current["fees"] += part_fee
            current["last_price"] = price
            current["trade_count"] += 1
            current["quantity"] = quantity
            if quantity == 0:
                current["exit"] = trade["date"]
                lots.clear()
            transactions.append(
                dict(
                    date=trade["date"],
                    price=price,
                    quantity=change,
                    value=change * price,
                    fee=part_fee,
                    kind=kind,
                    reason=trade["exit_reason"],
                    episode=current["id"],
                    after=quantity,
                )
            )
    for e in episodes:
        mark = e["last_price"] if e["exit"] else last_price
        e["mark_date"] = e["exit"] or last_date
        e["mark_price"] = mark
        e["price_change"] = mark / e["first_price"] - 1
        e["pnl"] = e["cash_flow"] + e["quantity"] * mark - e["fees"]
        e["unrealized"] = e["pnl"] - e["realized"]
        e["realized_return"] = e["realized"] / e["matched_cost"] if e["matched_cost"] else None
    return dict(trades=transactions, episodes=episodes)


def finite_json(value):
    """Strict JSON: no NaN/Infinity tokens and no ambiguous timestamp formats."""
    if isinstance(value, dict):
        return {str(k): finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [finite_json(v) for v in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NA or value is pd.NaT:
        return None
    return value
