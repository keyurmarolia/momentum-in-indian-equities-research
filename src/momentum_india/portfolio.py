"""Transparent next-open portfolio simulation for research portfolios."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .academic import prorated_borrow_cost
from .costs import delivery_buy_total_cost, delivery_order_costs
from .risk import align_cash_nav


@dataclass
class SimulationResult:
    daily: pd.DataFrame
    trades: pd.DataFrame


def _equal_capacity_waterfall(
    weights: pd.Series, symbols: list[str], amount: float, cap: float
) -> tuple[pd.Series, float]:
    """Spread an amount equally over eligible capacity, leaving any excess as cash."""
    remaining = max(float(amount), 0.0)
    active = sorted({symbol for symbol in symbols if weights.get(symbol, 0.0) < cap - 1e-12})
    while remaining > 1e-12 and active:
        equal_slice = remaining / len(active)
        used = 0.0
        next_active: list[str] = []
        for symbol in active:
            capacity = max(cap - float(weights.get(symbol, 0.0)), 0.0)
            addition = min(equal_slice, capacity)
            weights.loc[symbol] = float(weights.get(symbol, 0.0)) + addition
            used += addition
            if capacity - addition > 1e-12:
                next_active.append(symbol)
        if used <= 1e-12:
            break
        remaining -= used
        active = next_active
    return weights, remaining


def winner_drift_target_weights(
    current_weights: pd.Series,
    selected_symbols: list[str],
    requested_holdings_n: int,
    current_cash_weight: float = 0.0,
) -> pd.Series:
    """Create the strict-reconstitution winner-drift target at a scheduled rebalance.

    Continuing winners drift but are capped at 2/N. Exits and entrants are paired
    in stable symbol order. Each paired entrant receives the smaller of the exit's
    weight and 1/N; only the residual of an exit above 1/N is redistributed, equally
    and without rank preference, to continuing positions with room below 2/N.
    Unmatched entrants may use an existing cash sleeve, but never above 1/N.
    """
    if requested_holdings_n <= 0:
        raise ValueError("requested_holdings_n must be positive")
    selected = sorted(set(selected_symbols))
    if not selected:
        return pd.Series(dtype=float)
    slot, cap = 1.0 / requested_holdings_n, 2.0 / requested_holdings_n
    current = current_weights[current_weights.gt(0)].astype(float)
    if current.empty:
        return pd.Series(slot, index=selected, dtype=float)

    continuing = sorted(set(current.index).intersection(selected))
    exits = sorted(set(current.index).difference(selected))
    entrants = sorted(set(selected).difference(current.index))
    target = pd.Series(
        {symbol: min(float(current[symbol]), cap) for symbol in continuing}, dtype=float
    )
    residual = sum(max(float(current[symbol]) - cap, 0.0) for symbol in continuing)

    paired = min(len(exits), len(entrants))
    for exiting, entrant in zip(exits[:paired], entrants[:paired], strict=False):
        exit_weight = float(current[exiting])
        target.loc[entrant] = min(exit_weight, slot)
        residual += max(exit_weight - slot, 0.0)

    # A partially invested portfolio can expand from cash without manufacturing
    # leverage. All unmatched entrants share available cash equally.
    unmatched = entrants[paired:]
    cash_available = max(float(current_cash_weight), 0.0)
    if unmatched and cash_available > 0:
        per_entrant = min(slot, cash_available / len(unmatched))
        for entrant in unmatched:
            target.loc[entrant] = per_entrant

    target, _ = _equal_capacity_waterfall(target, continuing, residual, cap)
    return target.sort_index()


def academic_winner_drift_target_weights(
    current_weights: pd.Series, selected_weights: pd.Series, requested_holdings_n: int
) -> pd.Series:
    """Drift long and short JT legs separately while preserving 50/50 gross."""
    result: dict[str, float] = {}
    slot, cap = 1.0 / requested_holdings_n, 2.0 / requested_holdings_n
    for sign in (1.0, -1.0):
        selected = sorted(selected_weights[selected_weights.mul(sign).gt(0)].index)
        current = current_weights[current_weights.mul(sign).gt(0)].abs()
        weights = pd.Series(
            {s: min(float(current.get(s, slot)), cap) for s in selected}, dtype=float
        )
        if weights.sum() > 0.5:
            weights *= 0.5 / weights.sum()
        else:
            weights, _ = _equal_capacity_waterfall(weights, selected, 0.5 - weights.sum(), cap)
        result.update({symbol: sign * value for symbol, value in weights.items()})
    return pd.Series(result, dtype=float).sort_index()


def simulate_targets(
    market: pd.DataFrame,
    cash_nav: pd.Series,
    targets: pd.DataFrame,
    initial_capital: float = 1_000_000,
    apply_delivery_costs: bool = False,
    academic_borrow_rate: float = 0.0,
    execution_dates: pd.DatetimeIndex | None = None,
    maintenance_mode: str = "equal_weight",
    requested_holdings_n: int | None = None,
    forced_exit_signals: pd.DataFrame | None = None,
    terminal_events: pd.DataFrame | None = None,
    valuation_dates: pd.DatetimeIndex | None = None,
    open_panel: pd.DataFrame | None = None,
    close_panel: pd.DataFrame | None = None,
) -> SimulationResult:
    """Trade dated target weights at the open, then mark positions at the close.

    Signed negative weights are allowed only as an academic reference. Delivery
    costs must not be combined with negative targets because SLB execution is a
    different market mechanism.
    """
    required = {"date", "symbol", "open", "close"}
    if (open_panel is None or close_panel is None) and not required.issubset(market.columns):
        raise ValueError(f"Missing market fields: {sorted(required.difference(market.columns))}")
    required_targets = {"execution_date", "symbol", "weight"}
    if not required_targets.issubset(targets.columns):
        raise ValueError("Targets require execution_date, symbol, and weight")
    if apply_delivery_costs and targets["weight"].lt(0).any():
        raise ValueError("Delivery-equity costs cannot be applied to academic short weights")
    if maintenance_mode not in {"equal_weight", "winner_drift"}:
        raise ValueError("maintenance_mode must be equal_weight or winner_drift")
    if maintenance_mode == "winner_drift" and requested_holdings_n is None:
        raise ValueError("winner_drift requires requested_holdings_n")

    if (open_panel is None) != (close_panel is None):
        raise ValueError("open_panel and close_panel must be supplied together")
    if open_panel is None:
        frame = market.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        raw_opens = frame.pivot(index="date", columns="symbol", values="open").sort_index()
        raw_closes = frame.pivot(index="date", columns="symbol", values="close")
    else:
        raw_opens = open_panel.copy().sort_index()
        raw_closes = close_panel.copy().sort_index()
    if valuation_dates is not None:
        raw_opens = raw_opens.reindex(pd.DatetimeIndex(valuation_dates).sort_values().unique())
    raw_closes = raw_closes.reindex(index=raw_opens.index, columns=raw_opens.columns)
    closes = raw_closes.ffill()
    valuation_opens = raw_opens.combine_first(closes.shift(1)).combine_first(closes)
    cash = align_cash_nav(cash_nav, valuation_opens.index)
    if cash.isna().any():
        raise ValueError("Cash NAV must be known by the first valuation date")
    if cash.isna().any() or cash.le(0).any():
        raise ValueError("Cash NAV does not cover the simulation calendar")
    target_table = targets.copy()
    target_table["execution_date"] = pd.to_datetime(target_table["execution_date"])
    target_map = {
        day: group.set_index("symbol")["weight"].astype(float)
        for day, group in target_table.groupby("execution_date")
    }
    if execution_dates is not None:
        for day in pd.DatetimeIndex(execution_dates):
            target_map.setdefault(day, pd.Series(dtype=float))
    forced_map: dict[pd.Timestamp, set[str]] = {}
    if forced_exit_signals is not None and not forced_exit_signals.empty:
        forced = forced_exit_signals.copy()
        forced["execution_date"] = pd.to_datetime(forced["execution_date"])
        forced_map = {day: set(group["symbol"]) for day, group in forced.groupby("execution_date")}
    terminal_map: dict[pd.Timestamp, set[str]] = {}
    if terminal_events is not None and not terminal_events.empty:
        terminal = terminal_events.copy()
        terminal["execution_date"] = pd.to_datetime(terminal["execution_date"])
        terminal_map = {
            day: set(group["symbol"]) for day, group in terminal.groupby("execution_date")
        }

    units: dict[str, float] = {}
    cash_units = initial_capital / float(cash.iloc[0])
    pending_values: dict[str, float] = {}
    pending_quantities: dict[str, float | None] = {}
    pending_reasons: dict[str, str] = {}
    last_day = None
    daily_rows: list[dict] = []
    trade_rows: list[dict] = []
    for day in valuation_opens.index:
        nav = float(cash.loc[day])
        rebalance = day in target_map
        stop_symbols = forced_map.get(day, set()) if not rebalance else set()
        stop_exit = bool(stop_symbols.intersection(units))
        equity_before_rebalance = float("nan")
        transaction_cost = 0.0
        buy_value = 0.0
        sell_value = 0.0
        buy_orders = 0
        sell_orders = 0
        cost_components = {
            "brokerage": 0.0,
            "stt": 0.0,
            "exchange_transaction": 0.0,
            "sebi_turnover": 0.0,
            "ipft": 0.0,
            "stamp_duty": 0.0,
            "dp_charge": 0.0,
            "gst": 0.0,
        }

        # A confirmed delisting with no later exchange print has no executable
        # exit in the bhavcopy.  The principal result uses a conservative zero
        # recovery instead of carrying the last quote indefinitely.
        for symbol in sorted(terminal_map.get(day, set()).intersection(units)):
            old_units = units.pop(symbol)
            pending_values.pop(symbol, None)
            pending_quantities.pop(symbol, None)
            pending_reasons.pop(symbol, None)
            trade_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "price": 0.0,
                    "quantity_change": -old_units,
                    "trade_value": 0.0,
                    "exit_reason": "confirmed_delisting_zero_recovery",
                    **{f"cost_{key}": 0.0 for key in cost_components},
                    "allocated_cost": 0.0,
                }
            )

        if stop_exit:
            for symbol in sorted(stop_symbols.intersection(units)):
                pending_values[symbol] = 0.0
                pending_quantities[symbol] = 0.0
                pending_reasons[symbol] = "km_daily_stop"

        if rebalance:
            open_prices = valuation_opens.loc[day]
            current_value = {
                symbol: quantity * float(open_prices.get(symbol))
                for symbol, quantity in units.items()
                if pd.notna(open_prices.get(symbol))
            }
            equity_before = cash_units * nav + sum(current_value.values())
            equity_before_rebalance = equity_before
            weights = target_map[day]
            if maintenance_mode == "winner_drift":
                current_weights = pd.Series(current_value, dtype=float).div(equity_before)
                if weights.lt(0).any():
                    weights = academic_winner_drift_target_weights(
                        current_weights, weights, int(requested_holdings_n)
                    )
                else:
                    weights = winner_drift_target_weights(
                        current_weights=current_weights,
                        selected_symbols=list(weights.index),
                        requested_holdings_n=int(requested_holdings_n),
                        current_cash_weight=(cash_units * nav) / equity_before,
                    )
            if weights.abs().sum() > 1.0000001 and not weights.lt(0).any():
                raise ValueError(f"Long-only gross exposure exceeds 100% on {day.date()}")
            desired = (weights * equity_before).to_dict()
            pending_values = {
                symbol: float(desired.get(symbol, 0.0))
                for symbol in sorted(set(units).union(desired))
            }
            pending_quantities = {symbol: None for symbol in pending_values}
            pending_reasons = {symbol: "scheduled_rebalance" for symbol in pending_values}

        actual_prices = raw_opens.loc[day]
        available = [
            symbol
            for symbol in sorted(pending_values)
            if pd.notna(actual_prices.get(symbol)) and float(actual_prices.get(symbol)) > 0
        ]
        for symbol in available:
            if pending_quantities[symbol] is None:
                pending_quantities[symbol] = pending_values[symbol] / float(actual_prices[symbol])

        changes = {
            symbol: float(pending_quantities[symbol]) - float(units.get(symbol, 0.0))
            for symbol in available
        }

        def execute_batch(batch: dict[str, float], side: str, scale: float = 1.0) -> None:
            nonlocal cash_units, transaction_cost, buy_value, sell_value, buy_orders, sell_orders
            quantities = {
                symbol: quantity * scale
                for symbol, quantity in batch.items()
                if abs(quantity * scale) * float(actual_prices[symbol]) > 0.01
            }
            if not quantities:
                return
            values = pd.Series(
                {
                    symbol: abs(quantity) * float(actual_prices[symbol])
                    for symbol, quantity in quantities.items()
                },
                dtype=float,
            )
            if apply_delivery_costs:
                allocated = delivery_order_costs(values, pd.Series(side, index=values.index), day)
            else:
                allocated = pd.DataFrame(
                    0.0, index=values.index, columns=[*cost_components, "total"]
                )
            total_cost = float(allocated["total"].sum())
            transaction_cost += total_cost
            for key in cost_components:
                cost_components[key] += float(allocated[key].sum())
            if side == "sell":
                proceeds = float(values.sum())
                cash_units += (proceeds - total_cost) / nav
                sell_value += proceeds
                sell_orders += len(values)
            else:
                outlay = float(values.sum())
                cash_units -= (outlay + total_cost) / nav
                buy_value += outlay
                buy_orders += len(values)
            for symbol, quantity_change in quantities.items():
                old_units = float(units.get(symbol, 0.0))
                new_units = old_units + quantity_change
                if abs(new_units) < 1e-10:
                    units.pop(symbol, None)
                    new_units = 0.0
                else:
                    units[symbol] = new_units
                row_costs = allocated.loc[symbol]
                trade_rows.append(
                    {
                        "date": day,
                        "symbol": symbol,
                        "price": float(actual_prices[symbol]),
                        "quantity_change": quantity_change,
                        "trade_value": quantity_change * float(actual_prices[symbol]),
                        "exit_reason": pending_reasons[symbol],
                        **{f"cost_{key}": float(row_costs[key]) for key in cost_components},
                        "allocated_cost": float(row_costs["total"]),
                    }
                )

        sells = {symbol: change for symbol, change in changes.items() if change < -1e-12}
        execute_batch(sells, "sell")
        buys = {symbol: change for symbol, change in changes.items() if change > 1e-12}
        if buys:
            requested = sum(
                quantity * float(actual_prices[symbol]) for symbol, quantity in buys.items()
            )
            available_cash = max(cash_units * nav, 0.0)
            scale = min(1.0, available_cash / requested) if requested > 0 else 0.0
            if apply_delivery_costs and scale > 0:
                low, high = 0.0, scale
                base_values = [
                    quantity * float(actual_prices[symbol]) for symbol, quantity in buys.items()
                ]
                for _ in range(40):
                    mid = (low + high) / 2
                    cost = delivery_buy_total_cost(base_values, day, mid)
                    if requested * mid + cost <= available_cash:
                        low = mid
                    else:
                        high = mid
                scale = low
            execute_batch(buys, "buy", scale)
            if scale > 1e-12:
                # Trading costs or locked positions can make the scheduled
                # target unaffordable. The one-shot model accepts the partial
                # fill and leaves the residual in cash until the next rebalance
                # rather than manufacturing daily micro-orders.
                for symbol in buys:
                    pending_quantities[symbol] = float(units.get(symbol, 0.0))

        for symbol in available:
            target_quantity = pending_quantities.get(symbol)
            if target_quantity is None:
                continue
            if abs(float(units.get(symbol, 0.0)) - float(target_quantity)) <= 1e-8:
                pending_values.pop(symbol, None)
                pending_quantities.pop(symbol, None)
                pending_reasons.pop(symbol, None)

        close_prices = closes.loc[day]
        position_value = 0.0
        long_notional = 0.0
        short_notional = 0.0
        for symbol, quantity in units.items():
            price = close_prices.get(symbol)
            if pd.isna(price):
                price = valuation_opens.loc[day].get(symbol)
            value = quantity * float(price)
            position_value += value
            if value > 0:
                long_notional += value
            if value < 0:
                short_notional += -value
        borrow_cost = 0.0
        if last_day is not None and academic_borrow_rate > 0 and short_notional > 0:
            borrow_cost = prorated_borrow_cost(
                short_notional, academic_borrow_rate, (day - last_day).days
            )
            cash_units -= borrow_cost / nav
        equity = cash_units * nav + position_value
        daily_rows.append(
            {
                "date": day,
                "equity": equity,
                "cash_value": cash_units * nav,
                "long_exposure": long_notional / equity if equity != 0 else 0.0,
                "short_exposure": short_notional / equity if equity != 0 else 0.0,
                "borrow_cost": borrow_cost,
                "rebalance": rebalance,
                "stop_exit": stop_exit,
                "equity_before_rebalance": equity_before_rebalance,
                "transaction_cost": transaction_cost,
                "buy_value": buy_value,
                "sell_value": sell_value,
                "buy_orders": buy_orders,
                "sell_orders": sell_orders,
                **{f"cost_{key}": value for key, value in cost_components.items()},
                "unfilled_order_count": len(pending_values),
                "stale_position_count": sum(
                    pd.isna(raw_closes.loc[day].get(symbol)) for symbol in units
                ),
                "stale_position_value": sum(
                    abs(quantity * float(close_prices.get(symbol)))
                    for symbol, quantity in units.items()
                    if pd.isna(raw_closes.loc[day].get(symbol))
                ),
            }
        )
        last_day = day
    daily = pd.DataFrame(daily_rows).set_index("date")
    daily["return"] = daily["equity"].pct_change(fill_method=None)
    if not daily.empty:
        # The first execution day's open-to-close move and initial charges are
        # real P&L and must not be silently replaced with zero.
        daily.iloc[0, daily.columns.get_loc("return")] = (
            daily.iloc[0]["equity"] / initial_capital - 1.0
        )
    return SimulationResult(daily=daily, trades=pd.DataFrame(trade_rows))
