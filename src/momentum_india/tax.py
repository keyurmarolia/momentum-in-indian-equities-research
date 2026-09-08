from __future__ import annotations

import pandas as pd

from .rules import active_rules, load_rule_table


def financial_year(date: str | pd.Timestamp) -> str:
    date = pd.Timestamp(date)
    start = date.year if date.month >= 4 else date.year - 1
    return f"FY{start}-{str(start + 1)[-2:]}"


def grandfathered_equity_cost(
    actual_cost: float,
    fair_market_value_2018_01_31: float,
    sale_value: float,
) -> float:
    """Section 112A deemed cost: higher of actual cost and lower of FMV and sale value."""
    return max(actual_cost, min(fair_market_value_2018_01_31, sale_value))


def cess_rate_for(date: str | pd.Timestamp) -> float:
    rows = active_rules(load_rule_table("cess_rates"), date)
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one cess rule for {date}; found {len(rows)}")
    return float(rows.iloc[0]["cess_rate"])
