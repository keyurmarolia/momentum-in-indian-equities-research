from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from momentum_india.academic import prorated_borrow_cost
from momentum_india.config import PROJECT_ROOT
from momentum_india.corporate_actions import (
    adjust_prices_for_share_actions,
    build_share_action_table,
    share_multiplier_from_subject,
)
from momentum_india.costs import delivery_order_costs, delivery_trade_cost
from momentum_india.data.fyers_client import (
    FyersHistoryClient,
    RequestBudgetExceeded,
    daily_history_windows,
    plan_daily_history_requests,
)
from momentum_india.portfolio import simulate_targets, winner_drift_target_weights
from momentum_india.risk import historical_var_es, maximum_drawdown, performance_summary
from momentum_india.rules import load_rule_table
from momentum_india.schedules import rebalance_dates
from momentum_india.signals import jensen_alpha, raw_momentum, volatility_adjusted_momentum
from momentum_india.tax import cess_rate_for, financial_year, grandfathered_equity_cost
from momentum_india.tax_ledger import annual_equity_tax, fifo_realizations
from momentum_india.universe import capacity_eligible, required_mdtv_for_position


def _zip_csv(name: str, csv_text: str) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, csv_text)
    return buffer.getvalue()


def test_absolute_liquidity_capacity_rule() -> None:
    threshold = required_mdtv_for_position(50_000_000, 12, 0.05)
    assert threshold == pytest.approx(83_333_333.33333333)
    mdtv = pd.Series({"A": 100_000_000, "B": threshold, "C": 80_000_000})
    assert capacity_eligible(mdtv, threshold).tolist() == ["A", "B"]


def test_nse_legacy_bhavcopy_normalization_keeps_mainboard_eq_only() -> None:
    from scripts.download_nse_bulk_equities import normalize_bhavcopy

    content = _zip_csv(
        "cm01JAN2020bhav.csv",
        "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,ISIN\n"
        "AAA,EQ,100,110,99,108,1000,105000,01-JAN-2020,INE000A01001\n"
        "BBB,BE,10,11,9,10,2000,20000,01-JAN-2020,INE000B01001\n",
    )
    result = normalize_bhavcopy(content, "legacy")
    assert result["symbol"].tolist() == ["NSE:AAA-EQ"]
    assert result.iloc[0]["official_traded_value_inr"] == 105_000


def test_nse_udiff_bhavcopy_normalization_keeps_mainboard_eq_only() -> None:
    from scripts.download_nse_bulk_equities import normalize_bhavcopy

    content = _zip_csv(
        "BhavCopy.csv",
        "TradDt,TckrSymb,SctySrs,ISIN,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol,TtlTrfVal\n"
        "2026-08-20,AAA,EQ,INE000A01001,100,110,99,108,1000,105000\n"
        "2026-08-20,SME,SM,INE000S01001,10,11,9,10,2000,20000\n",
    )
    result = normalize_bhavcopy(content, "udiff")
    assert result["symbol"].tolist() == ["NSE:AAA-EQ"]


def test_explicit_split_and_bonus_parsing() -> None:
    assert share_multiplier_from_subject("Fv Split Rs.10/- To Rs.2/")["share_multiplier"] == 5
    assert share_multiplier_from_subject("Bonus 1:2")["share_multiplier"] == 1.5
    assert (
        share_multiplier_from_subject("Bonus Shares In The Ratio Of 1:1")["share_multiplier"] == 2
    )
    assert share_multiplier_from_subject("Bonus Debentures 1:1")["share_multiplier"] is None
    assert share_multiplier_from_subject("Sch Of Agmt- Bonus Deb1:1")["share_multiplier"] is None
    assert share_multiplier_from_subject("Spl-Rs10 To Rs2/Bonus-1:2")[
        "share_multiplier"
    ] == pytest.approx(7.5)
    assert share_multiplier_from_subject("Fv Spl-Rs10tors5/Bon-2:1")[
        "share_multiplier"
    ] == pytest.approx(6.0)
    assert share_multiplier_from_subject("Dividend - Rs 10 Per Share")["share_multiplier"] is None


def test_share_actions_are_deduplicated_and_back_adjust_prices() -> None:
    records = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "series": ["EQ", "EQ"],
            "subject": ["Bonus 1:1", "Bonus 1:1"],
            "exDate": ["02-Jan-2024", "02-Jan-2024"],
        }
    )
    actions = build_share_action_table(records)
    assert len(actions) == 1 and actions.iloc[0]["share_multiplier"] == 2
    market = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "symbol": ["NSE:AAA-EQ", "NSE:AAA-EQ"],
            "nse_symbol": ["AAA", "AAA"],
            "open": [100.0, 50.0],
            "high": [100.0, 50.0],
            "low": [100.0, 50.0],
            "close": [100.0, 50.0],
        }
    )
    adjusted = adjust_prices_for_share_actions(market, actions)
    assert adjusted["close"].tolist() == [50.0, 50.0]


def test_same_day_split_and_bonus_are_both_applied() -> None:
    records = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "series": ["EQ", "EQ"],
            "subject": ["Bonus 1:1", "Face Value Split From Rs 2 To Re 1"],
            "exDate": ["02-Jan-2024", "02-Jan-2024"],
        }
    )
    actions = build_share_action_table(records)
    assert actions.iloc[0]["share_multiplier"] == 4


def test_financial_year_boundary() -> None:
    assert financial_year("2024-03-31") == "FY2023-24"
    assert financial_year("2024-04-01") == "FY2024-25"


def test_grandfathered_cost_formula() -> None:
    assert grandfathered_equity_cost(80, 120, 100) == 100
    assert grandfathered_equity_cost(110, 120, 100) == 110


def test_historical_cess_lookup() -> None:
    assert cess_rate_for("2004-03-31") == 0.0
    assert cess_rate_for("2004-04-01") == 0.02
    assert cess_rate_for("2018-04-01") == 0.04


def test_current_cost_bridge_reconciles() -> None:
    result = delivery_trade_cost(100_000, 120_000, sold_isins=1)
    assert result["total"] == sum(v for k, v in result.items() if k != "total")
    assert result["stt"] == 220.0
    assert result["stamp_duty"] == pytest.approx(15.0)


def test_fyers_delivery_calculator_example_reconciles() -> None:
    before_dp = delivery_trade_cost(1_000_000, 1_100_000, sold_isins=0)
    with_dp = delivery_trade_cost(1_000_000, 1_100_000, sold_isins=1)
    assert before_dp["brokerage"] == pytest.approx(40.0)
    assert before_dp["stt"] == pytest.approx(2_100.0)
    assert before_dp["exchange_transaction"] == pytest.approx(64.4679)
    assert before_dp["sebi_turnover"] == pytest.approx(2.10)
    assert before_dp["stamp_duty"] == pytest.approx(150.0)
    assert before_dp["gst"] == pytest.approx(19.1826)
    assert before_dp["total"] == pytest.approx(2_375.7526)
    assert with_dp["total"] == pytest.approx(2_390.5026)


def test_brokerage_uses_each_executed_order_value() -> None:
    result = delivery_trade_cost(
        10_000,
        10_000,
        buy_orders=2,
        sell_orders=2,
        buy_order_values=[5_000, 5_000],
        sell_order_values=[5_000, 5_000],
    )
    assert result["brokerage"] == pytest.approx(60.0)


def test_signal_definitions() -> None:
    index = pd.bdate_range("2023-01-02", periods=253)
    close = pd.DataFrame(
        {"A": np.linspace(100, 120, 253), "B": np.linspace(100, 90, 253)}, index=index
    )
    raw = raw_momentum(close)
    adjusted = volatility_adjusted_momentum(close)
    assert raw["A"] > 0 and raw["B"] < 0
    assert adjusted.index.tolist() == ["A", "B"]


def test_jensen_alpha_accepts_investable_reference_returns() -> None:
    index = pd.bdate_range("2024-01-01", periods=10)
    market = pd.Series(np.linspace(-0.01, 0.01, 10), index=index)
    reference = pd.Series(0.0002, index=index)
    stocks = pd.DataFrame({"A": 0.001 + 1.2 * (market - reference) + reference}, index=index)
    alpha = jensen_alpha(stocks, market, reference)
    assert alpha["A"] == pytest.approx(0.001)


def test_vectorized_jensen_alpha_handles_column_specific_missing_values() -> None:
    index = pd.bdate_range("2024-01-01", periods=5)
    market = pd.Series([-0.01, 0.00, 0.01, 0.02, -0.02], index=index)
    reference = pd.Series(0.0001, index=index)
    stocks = pd.DataFrame(
        {
            "A": 0.002 + 0.8 * (market - reference) + reference,
            "B": 0.003 + 1.1 * (market - reference) + reference,
        },
        index=index,
    )
    stocks.loc[index[0], "B"] = np.nan
    alpha = jensen_alpha(stocks, market, reference)
    assert alpha["A"] == pytest.approx(0.002)
    assert alpha["B"] == pytest.approx(0.003)


def test_academic_borrow_cost() -> None:
    assert prorated_borrow_cost(500_000, 0.06, 365) == pytest.approx(30_000)


def test_next_open_simulation_and_borrow_cost_guardrail() -> None:
    dates = pd.bdate_range("2024-01-01", periods=3)
    market = pd.DataFrame(
        {
            "date": list(dates) * 1,
            "symbol": ["A"] * 3,
            "open": [100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 103.0],
        }
    )
    targets = pd.DataFrame({"execution_date": [dates[0]], "symbol": ["A"], "weight": [1.0]})
    cash = pd.Series(10.0, index=dates)
    result = simulate_targets(market, cash, targets, initial_capital=100_000)
    assert result.daily.iloc[-1]["equity"] == pytest.approx(103_000)
    assert result.daily.iloc[0]["return"] == pytest.approx(0.01)
    short = targets.assign(weight=-0.5)
    with pytest.raises(ValueError, match="Delivery-equity costs"):
        simulate_targets(market, cash, short, apply_delivery_costs=True)


def test_delivery_costs_do_not_create_negative_cash_or_hidden_first_day_loss() -> None:
    dates = pd.bdate_range("2024-01-01", periods=2)
    market = pd.DataFrame(
        {"date": dates, "symbol": ["A", "A"], "open": [100.0, 100.0], "close": [100.0, 100.0]}
    )
    targets = pd.DataFrame({"execution_date": [dates[0]], "symbol": ["A"], "weight": [1.0]})
    result = simulate_targets(
        market,
        pd.Series(10.0, index=dates),
        targets,
        initial_capital=100_000,
        apply_delivery_costs=True,
    )
    assert result.daily.iloc[0]["cash_value"] >= -0.01
    assert result.daily.iloc[0]["return"] < 0.0


def test_floating_point_dust_does_not_create_a_fee_bearing_order() -> None:
    dates = pd.bdate_range("2024-01-01", periods=3)
    market = pd.DataFrame(
        {"date": dates, "symbol": ["A"] * 3, "open": [100.0] * 3, "close": [100.0] * 3}
    )
    cash = pd.Series(10.0, index=dates)
    first_target = pd.DataFrame({"execution_date": [dates[0]], "symbol": ["A"], "weight": [0.5]})
    first = simulate_targets(
        market, cash, first_target, initial_capital=100_000, apply_delivery_costs=True
    )
    units = float(first.trades.iloc[0].quantity_change)
    unchanged_weight = units * 100.0 / float(first.daily.loc[dates[0], "equity"])
    targets = pd.DataFrame(
        {
            "execution_date": [dates[0], dates[1]],
            "symbol": ["A", "A"],
            "weight": [0.5, unchanged_weight + 1e-12],
        }
    )
    result = simulate_targets(
        market, cash, targets, initial_capital=100_000, apply_delivery_costs=True
    )
    assert len(result.trades) == 1
    assert result.daily.loc[dates[1], "transaction_cost"] == pytest.approx(0.0)


def test_suspended_security_exits_only_at_its_next_observed_open() -> None:
    dates = pd.bdate_range("2024-01-01", periods=3)
    market = pd.DataFrame(
        [
            {"date": dates[0], "symbol": "A", "open": 100.0, "close": 100.0},
            {"date": dates[1], "symbol": "B", "open": 50.0, "close": 50.0},
            {"date": dates[2], "symbol": "A", "open": 80.0, "close": 80.0},
        ]
    )
    targets = pd.DataFrame({"execution_date": [dates[0]], "symbol": ["A"], "weight": [1.0]})
    result = simulate_targets(
        market,
        pd.Series(10.0, index=dates),
        targets,
        execution_dates=dates[:2],
        valuation_dates=dates,
        initial_capital=100_000,
    )
    exits = result.trades.loc[result.trades["quantity_change"].lt(0)]
    assert exits["date"].tolist() == [dates[2]]
    assert exits["price"].tolist() == [80.0]


def test_confirmed_delisting_is_not_carried_at_a_stale_quote() -> None:
    dates = pd.bdate_range("2024-01-01", periods=2)
    market = pd.DataFrame([{"date": dates[0], "symbol": "A", "open": 100.0, "close": 100.0}])
    targets = pd.DataFrame({"execution_date": [dates[0]], "symbol": ["A"], "weight": [1.0]})
    terminal = pd.DataFrame({"execution_date": [dates[1]], "symbol": ["A"]})
    result = simulate_targets(
        market,
        pd.Series(10.0, index=dates),
        targets,
        terminal_events=terminal,
        valuation_dates=dates,
        initial_capital=100_000,
    )
    assert result.daily.loc[dates[1], "equity"] == pytest.approx(0.0)
    assert result.trades.iloc[-1]["exit_reason"] == "confirmed_delisting_zero_recovery"


def test_order_level_cost_allocation_reconciles_to_cost_bridge() -> None:
    values = pd.Series({"BUY": 1_000_000.0, "SELL": 1_100_000.0})
    sides = pd.Series({"BUY": "buy", "SELL": "sell"})
    allocated = delivery_order_costs(values, sides, pd.Timestamp("2026-08-29"))
    bridge = delivery_trade_cost(
        1_000_000,
        1_100_000,
        sold_isins=1,
        trade_date=pd.Timestamp("2026-08-29"),
    )
    assert allocated["total"].sum() == pytest.approx(bridge["total"])


def test_winner_drift_pairs_exits_caps_winners_and_uses_equal_waterfall() -> None:
    current = pd.Series({"A": 0.25, "B": 0.18, "C": 0.07, "EXIT": 0.30})
    result = winner_drift_target_weights(
        current,
        ["A", "B", "C", "NEW"],
        requested_holdings_n=10,
        current_cash_weight=0.20,
    )
    # A is trimmed to the 2/N cap. NEW receives only 1/N from the 0.30 exit.
    # The exit residual and cap trim are shared mechanically among continuing
    # names with capacity; no signal rank is consulted.
    assert result["NEW"] == pytest.approx(0.10)
    assert result.max() <= 0.20 + 1e-12
    assert result["A"] == pytest.approx(0.20)
    assert result["B"] == pytest.approx(0.20)
    assert result["C"] == pytest.approx(0.20)


def test_winner_drift_small_exit_gives_entrant_same_small_weight() -> None:
    current = pd.Series({"KEEP": 0.15, "EXIT": 0.04})
    result = winner_drift_target_weights(
        current,
        ["KEEP", "NEW"],
        requested_holdings_n=10,
        current_cash_weight=0.81,
    )
    assert result["KEEP"] == pytest.approx(0.15)
    assert result["NEW"] == pytest.approx(0.04)


def test_fifo_realization_and_annual_tax_netting() -> None:
    trades = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-02", "2023-06-01"]),
            "symbol": ["A", "A"],
            "price": [100.0, 120.0],
            "quantity_change": [10.0, -10.0],
        }
    )
    realized = fifo_realizations(trades)
    assert realized.iloc[0]["realized_gain"] == pytest.approx(200.0)
    taxes = annual_equity_tax(realized)
    assert taxes.iloc[0]["total_tax"] > 0


def test_holding_period_uses_twelve_calendar_months() -> None:
    trades = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-03-01", "2023-03-01", "2024-03-01", "2024-03-02"]),
            "symbol": ["A", "B", "A", "B"],
            "price": [100.0, 100.0, 110.0, 110.0],
            "quantity_change": [1.0, 1.0, -1.0, -1.0],
        }
    )
    realized = fifo_realizations(trades)
    assert realized.set_index("symbol").loc["A", "holding_class"] == "short_term"
    assert realized.set_index("symbol").loc["B", "holding_class"] == "long_term"


def test_short_term_loss_is_carried_forward_and_offsets_later_gain() -> None:
    realized = pd.DataFrame(
        {
            "sale_date": pd.to_datetime(["2019-01-10", "2020-01-10"]),
            "holding_class": ["short_term", "short_term"],
            "realized_gain": [-100.0, 200.0],
            "financial_year": ["FY2018-19", "FY2019-20"],
        }
    )
    taxes = annual_equity_tax(realized).set_index("financial_year")
    assert taxes.loc["FY2018-19", "short_term_loss_carryforward"] == pytest.approx(100.0)
    assert taxes.loc["FY2019-20", "short_term_taxable_gain"] == pytest.approx(100.0)


def test_rebalance_dates_are_last_trading_dates() -> None:
    dates = pd.bdate_range("2024-01-01", "2024-12-31")
    quarterly = rebalance_dates(dates, "3M")
    assert quarterly.strftime("%Y-%m-%d").tolist() == [
        "2024-03-29",
        "2024-06-28",
        "2024-09-30",
        "2024-12-31",
    ]


def test_risk_sign_convention() -> None:
    returns = pd.Series([-0.10, -0.05, 0.01, 0.02, 0.03])
    result = historical_var_es(returns, confidence=0.8)
    assert result["var"] > 0
    assert result["es"] > 0
    assert maximum_drawdown(returns) <= 0
    summary = performance_summary(
        pd.Series(returns.values, index=pd.bdate_range("2024-01-01", periods=5))
    )
    assert summary["monthly_var_95"] > 0 and summary["maximum_drawdown"] <= 0


def test_history_windows_are_bounded_and_contiguous() -> None:
    windows = list(daily_history_windows(date(2020, 1, 1), date(2022, 1, 1)))
    assert all((right - left).days + 1 <= 366 for left, right in windows)
    assert all(
        windows[i][1].toordinal() + 1 == windows[i + 1][0].toordinal()
        for i in range(len(windows) - 1)
    )


def test_fyers_cache_prevents_duplicate_calls(tmp_path) -> None:
    calls = []

    def fake(payload):
        calls.append(payload)
        return {"s": "ok", "code": 200, "candles": []}

    client = FyersHistoryClient(fake, tmp_path)
    payload = {"symbol": "NSE:SBIN-EQ", "resolution": "D"}
    client.history(payload)
    client.history(payload)
    assert len(calls) == 1


def test_fyers_429_stops_without_retry(tmp_path) -> None:
    calls = []

    def fake(payload):
        calls.append(payload)
        return {"s": "error", "code": 429, "message": "request limit reached"}

    client = FyersHistoryClient(fake, tmp_path)
    try:
        client.history({"symbol": "NSE:SBIN-EQ"})
    except RequestBudgetExceeded:
        pass
    else:
        raise AssertionError("Expected fail-closed behavior")
    assert len(calls) == 1


def test_fyers_no_data_is_cached_without_repeat(tmp_path) -> None:
    calls = []

    def fake(payload):
        calls.append(payload)
        return {"s": "no_data", "code": -300, "message": "Data doesn't exist", "candles": []}

    client = FyersHistoryClient(fake, tmp_path)
    payload = {"symbol": "NSE:NEW-EQ", "resolution": "D"}
    assert client.history(payload)["s"] == "no_data"
    assert client.history(payload)["s"] == "no_data"
    assert len(calls) == 1


def test_preflight_plan_makes_no_calls_and_counts_windows(tmp_path) -> None:
    plan = plan_daily_history_requests(
        ["NSE:SBIN-EQ", "NSE:INFY-EQ"], date(2024, 1, 1), date(2025, 1, 1), tmp_path
    )
    assert plan["symbols"] == 2
    assert plan["missing_windows"] == 4
    assert plan["cached_windows"] == 0


def test_equity_tax_boundary_rates_and_fy2024_threshold() -> None:
    table = load_rule_table("equity_capital_gains")

    def rule(day: str, holding: str):
        when = pd.Timestamp(day)
        rows = table.loc[
            table["holding_class"].eq(holding)
            & table["effective_from"].le(when)
            & (table["effective_to"].isna() | table["effective_to"].ge(when))
        ]
        assert len(rows) == 1
        return rows.iloc[0]

    assert float(rule("2008-03-31", "short_term")["tax_rate"]) == 0.10
    assert float(rule("2008-04-01", "short_term")["tax_rate"]) == 0.15
    assert float(rule("2024-07-22", "short_term")["tax_rate"]) == 0.15
    assert float(rule("2024-07-23", "short_term")["tax_rate"]) == 0.20
    assert int(rule("2024-04-01", "long_term")["exemption_threshold"]) == 125_000
    assert float(rule("2024-07-23", "long_term")["tax_rate"]) == 0.125


def test_debt_fund_2014_and_2024_boundaries() -> None:
    table = load_rule_table("debt_fund_capital_gains")
    old = table.loc[table["rule_id"].eq("DF_PRE_2014_LTCG_NO_INDEX")].iloc[0]
    reform = table.loc[table["rule_id"].eq("DF_2014_LTCG")].iloc[0]
    legacy = table.loc[table["rule_id"].eq("DF_POST_2024_LEGACY")].iloc[0]
    assert old["effective_to"] == pd.Timestamp("2014-07-10")
    assert reform["effective_from"] == pd.Timestamp("2014-07-11")
    assert int(reform["holding_period_days"]) == 1095 and bool(reform["indexation"])
    assert int(legacy["holding_period_days"]) == 730
    assert float(legacy["tax_rate"]) == 0.125 and not bool(legacy["indexation"])


def test_historical_stt_boundaries() -> None:
    table = pd.read_csv(
        PROJECT_ROOT / "data" / "reference" / "trading_cost_history.csv",
        parse_dates=["effective_from", "effective_to"],
    )
    table = table.loc[table["component"].eq("STT")]

    def rate(day: str) -> float:
        when = pd.Timestamp(day)
        rows = table.loc[
            table["effective_from"].le(when)
            & (table["effective_to"].isna() | table["effective_to"].ge(when))
        ]
        assert len(rows) == 1
        return float(rows.iloc[0]["buy_rate"])

    assert rate("2004-09-30") == 0
    assert rate("2004-10-01") == 0.075
    assert rate("2006-06-01") == 0.125
    assert rate("2012-07-01") == 0.10
