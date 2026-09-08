"""FIFO listed-equity realization ledger and annual research tax aggregation."""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

from .rules import active_rules, load_rule_table
from .tax import cess_rate_for, financial_year, grandfathered_equity_cost


def fifo_realizations(trades: pd.DataFrame, fmv_2018: pd.Series | None = None) -> pd.DataFrame:
    lots: dict[str, deque[dict]] = defaultdict(deque)
    rows: list[dict] = []
    for trade in trades.sort_values(["date", "symbol"]).itertuples():
        quantity = float(trade.quantity_change)
        allocated_cost = float(getattr(trade, "allocated_cost", 0.0) or 0.0)
        stt = float(getattr(trade, "cost_stt", 0.0) or 0.0)
        deductible_expense = max(allocated_cost - stt, 0.0)
        if quantity > 0:
            lots[trade.symbol].append(
                {
                    "date": pd.Timestamp(trade.date),
                    "quantity": quantity,
                    "price": float(trade.price),
                    "remaining_expense": deductible_expense,
                }
            )
            continue
        remaining = -quantity
        sale_quantity = remaining
        rounding_tolerance = max(1e-8, remaining * 1e-10)
        while remaining > 1e-10:
            if not lots[trade.symbol]:
                if remaining <= rounding_tolerance:
                    break
                raise ValueError(f"Sale exceeds long inventory for {trade.symbol} on {trade.date}")
            lot = lots[trade.symbol][0]
            used = min(remaining, lot["quantity"])
            actual_cost = lot["price"]
            sale_price = float(trade.price)
            deemed_cost = actual_cost
            if (
                lot["date"] <= pd.Timestamp("2018-01-31")
                and pd.Timestamp(trade.date) >= pd.Timestamp("2018-04-01")
                and pd.Timestamp(trade.date) > lot["date"] + pd.DateOffset(months=12)
                and fmv_2018 is not None
            ):
                fmv = fmv_2018.get(trade.symbol)
                if pd.notna(fmv):
                    deemed_cost = grandfathered_equity_cost(actual_cost, float(fmv), sale_price)
            acquisition_expense = lot["remaining_expense"] * used / lot["quantity"]
            transfer_expense = deductible_expense * used / sale_quantity if sale_quantity else 0.0
            rows.append(
                {
                    "symbol": trade.symbol,
                    "taxable_disposal": getattr(trade, "exit_reason", "")
                    != "confirmed_delisting_zero_recovery",
                    "acquisition_date": lot["date"],
                    "sale_date": pd.Timestamp(trade.date),
                    "quantity": used,
                    "sale_value": used * sale_price,
                    "transfer_expense": transfer_expense,
                    "cost_basis": used * deemed_cost + acquisition_expense,
                    "realized_gain": used * sale_price
                    - transfer_expense
                    - used * deemed_cost
                    - acquisition_expense,
                    "holding_period_days": (pd.Timestamp(trade.date) - lot["date"]).days,
                }
            )
            lot["remaining_expense"] -= acquisition_expense
            lot["quantity"] -= used
            remaining -= used
            if lot["quantity"] <= 1e-10:
                lots[trade.symbol].popleft()
    result = pd.DataFrame(rows)
    if not result.empty:
        anniversary = result["acquisition_date"] + pd.DateOffset(months=12)
        result["holding_class"] = (
            result["sale_date"].gt(anniversary).map({True: "long_term", False: "short_term"})
        )
        result["financial_year"] = result["sale_date"].map(financial_year)
    return result


def annual_equity_tax(realized: pd.DataFrame) -> pd.DataFrame:
    """Estimate annual listed-equity tax with eight-year loss carry-forwards.

    Long-term losses offset only long-term gains. Short-term losses then offset
    either class, with expiring losses consumed first and higher-rate gains
    reduced first. The Section 112A threshold is applied to the remaining
    long-term gain buckets before cess.
    """
    if "taxable_disposal" in realized:
        # A valuation write-down is not evidence of a legally realized loss.
        realized = realized.loc[realized.taxable_disposal].copy()
    if realized.empty:
        return pd.DataFrame(columns=["financial_year", "base_tax", "cess", "total_tax"])
    rules = load_rule_table("equity_capital_gains")
    output: list[dict] = []
    carry_short: list[dict[str, float | int]] = []
    carry_long: list[dict[str, float | int]] = []

    def fy_index(label: str) -> int:
        return int(str(label)[2:6])

    def consume_loss(pool: list[dict[str, float | int]], amount: float) -> float:
        remaining = amount
        for item in sorted(pool, key=lambda value: int(value["origin"])):
            used = min(float(item["amount"]), remaining)
            item["amount"] = float(item["amount"]) - used
            remaining -= used
            if remaining <= 1e-10:
                break
        pool[:] = [item for item in pool if float(item["amount"]) > 1e-10]
        return remaining

    def reduce_buckets(buckets: list[dict[str, float]], amount: float) -> float:
        remaining = amount
        for bucket in sorted(buckets, key=lambda value: value["rate"], reverse=True):
            used = min(bucket["gain"], remaining)
            bucket["gain"] -= used
            remaining -= used
            if remaining <= 1e-10:
                break
        return remaining

    for fy, group in sorted(realized.groupby("financial_year"), key=lambda pair: fy_index(pair[0])):
        index = fy_index(fy)
        carry_short = [item for item in carry_short if index - int(item["origin"]) <= 8]
        carry_long = [item for item in carry_long if index - int(item["origin"]) <= 8]
        buckets = {"short_term": [], "long_term": []}
        losses = {"short_term": 0.0, "long_term": 0.0}
        threshold = 0.0
        # Aggregate equal-date, equal-class gains and losses separately. This
        # preserves the loss-allocation rule without repeated per-lot lookups.
        grouped = (
            group.assign(loss=group.realized_gain.lt(0))
            .groupby(["sale_date", "holding_class", "loss"], as_index=False)
            .realized_gain.sum()
        )
        for row in grouped.itertuples():
            gain = float(row.realized_gain)
            holding = row.holding_class
            if holding == "long_term" and pd.Timestamp(
                "2004-10-01"
            ) <= row.sale_date <= pd.Timestamp("2018-03-31"):
                # Exempt Section 10(38) disposals do not consume taxable losses
                # or create a loss carry-forward.
                continue
            if gain <= 0:
                losses[holding] += -gain
                continue
            active = active_rules(rules.loc[rules["holding_class"].eq(holding)], row.sale_date)
            if holding == "long_term" and len(active) > 1:
                active = active.loc[~active["indexation"]]
            if len(active) != 1:
                raise ValueError(f"Ambiguous {holding} equity rule on {row.sale_date}")
            rate = active.iloc[0]["tax_rate"]
            rate = 0.30 if rate == "ordinary_marginal" else float(rate)
            buckets[holding].append({"gain": gain, "rate": rate})
            threshold = max(threshold, float(active.iloc[0]["exemption_threshold"]))

        if losses["long_term"] > 0:
            carry_long.append({"origin": index, "amount": losses["long_term"]})
        available_long_loss = sum(float(item["amount"]) for item in carry_long)
        unused = reduce_buckets(buckets["long_term"], available_long_loss)
        consume_loss(carry_long, available_long_loss - unused)

        if losses["short_term"] > 0:
            carry_short.append({"origin": index, "amount": losses["short_term"]})
        available_short_loss = sum(float(item["amount"]) for item in carry_short)
        eligible = [*buckets["short_term"], *buckets["long_term"]]
        unused = reduce_buckets(eligible, available_short_loss)
        consume_loss(carry_short, available_short_loss - unused)

        remaining_threshold = threshold
        for bucket in sorted(buckets["long_term"], key=lambda value: value["rate"], reverse=True):
            used = min(bucket["gain"], remaining_threshold)
            bucket["gain"] -= used
            remaining_threshold -= used
        short_taxable = sum(bucket["gain"] for bucket in buckets["short_term"])
        long_taxable = sum(bucket["gain"] for bucket in buckets["long_term"])
        base = sum(
            bucket["gain"] * bucket["rate"]
            for bucket in [*buckets["short_term"], *buckets["long_term"]]
        )
        last_sale = group["sale_date"].max()
        cess = base * cess_rate_for(last_sale)
        output.append(
            {
                "financial_year": fy,
                "base_tax": base,
                "cess": cess,
                "total_tax": base + cess,
                "short_term_taxable_gain": short_taxable,
                "long_term_taxable_gain": long_taxable,
                "ltcg_exemption_used": threshold - remaining_threshold,
                "short_term_loss_carryforward": sum(float(item["amount"]) for item in carry_short),
                "long_term_loss_carryforward": sum(float(item["amount"]) for item in carry_long),
            }
        )
    return pd.DataFrame(output)
