"""Tests for KM rules, drift constraints and date-specific costs."""

import numpy as np
import pandas as pd
import pytest

from momentum_india.costs import delivery_trade_cost
from momentum_india.portfolio import academic_winner_drift_target_weights, simulate_targets
from momentum_india.risk import (
    drawdown_episode_table,
    historical_var_es,
    maximum_drawdown,
    performance_summary,
)
from momentum_india.signals import exponential_moving_average, supertrend, wilder_atr


def test_initial_capital_drawdown_and_open_episode():
    dates = pd.bdate_range("2024-01-01", periods=4)
    values = pd.Series([-0.1, 0, 0.02, 0], index=dates)
    assert maximum_drawdown(values) == pytest.approx(-0.1)
    episode = drawdown_episode_table(values).iloc[0]
    assert episode.trading_days == 4
    assert pd.isna(episode.peak_date) and pd.isna(episode.recovery_date)
    assert episode.trough_date == dates[0]


def test_drawdown_recovery_and_sharpe_definition():
    dates = pd.bdate_range("2024-01-01", periods=5)
    values = pd.Series([0.1, -0.1, 1 / 9, 0.01, -0.01], index=dates)
    episodes = drawdown_episode_table(values)
    assert len(episodes) == 2
    assert episodes.iloc[0].trading_days == 1
    assert episodes.iloc[0].recovery_date == dates[2]
    assert pd.isna(episodes.iloc[1].recovery_date)
    reference = pd.Series([0.001, 0.002, 0.001, 0.003, 0.001], index=dates)
    excess = values - reference
    assert performance_summary(values, reference)["sharpe"] == pytest.approx(
        excess.mean() / excess.std() * np.sqrt(252)
    )


def test_tail_risk_reports_loss_and_tail_mean():
    values = pd.Series([-0.2, -0.1, 0, 0.1, 0.2])
    r = historical_var_es(values, 0.8)
    assert r["var"] == pytest.approx(0.12)
    assert r["es"] == pytest.approx(0.2)


def test_ema_seed_and_recursive_value():
    close = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0, 5.0]})
    actual = exponential_moving_average(close, 3).A
    assert actual.iloc[:2].isna().all()
    assert actual.iloc[2:].tolist() == pytest.approx([2, 3, 4])


def test_wilder_seed_and_gap():
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0, 16.0, 15.0]})
    atr = wilder_atr(close + 1, close - 1, close, 2).A
    assert atr.iloc[:2].isna().all()
    assert atr.iloc[2:].tolist() == pytest.approx([2.0, 3.5, 2.75])


def test_indicator_prefix_causality_and_missing_bar():
    close = pd.DataFrame({"A": np.r_[np.arange(20.0, 50.0), np.arange(48.0, 15.0, -1)]})
    line, bull = supertrend(close + 1, close - 1, close, 10, 3)
    earlier = supertrend(close.iloc[:40] + 1, close.iloc[:40] - 1, close.iloc[:40], 10, 3)
    pd.testing.assert_frame_equal(line.iloc[:40], earlier[0])
    pd.testing.assert_frame_equal(bull.iloc[:40], earlier[1])
    assert bull.iloc[20, 0] and not bull.iloc[-1, 0]
    missing = close.reindex(sorted(list(close.index) + [21.5]))
    mline, _ = supertrend(missing + 1, missing - 1, missing, 10, 3)
    np.testing.assert_allclose(mline.drop(index=21.5).A, line.A, equal_nan=True)


def test_km_stop_leaves_cash_and_does_not_resize_other_stock():
    dates = pd.bdate_range("2024-01-01", periods=5)
    market = pd.DataFrame(
        [{"date": d, "symbol": s, "open": 100.0, "close": 100.0} for d in dates for s in ["A", "B"]]
    )
    targets = pd.DataFrame(
        {
            "execution_date": [dates[0], dates[0], dates[4], dates[4]],
            "symbol": ["A", "B", "A", "B"],
            "weight": [0.5] * 4,
        }
    )
    stop = pd.DataFrame({"execution_date": [dates[2]], "symbol": ["A"]})
    r = simulate_targets(
        market,
        pd.Series(10.0, index=dates),
        targets,
        initial_capital=100000,
        forced_exit_signals=stop,
    )
    assert r.daily.loc[dates[2], "cash_value"] == 50000
    assert r.daily.loc[dates[3], "cash_value"] == 50000
    assert r.daily.loc[dates[4], "cash_value"] == 0
    assert r.trades.loc[r.trades.date.eq(dates[2]), "symbol"].tolist() == ["A"]
    assert not r.trades.date.eq(dates[3]).any()


def test_stop_charges_are_actual_sale_only():
    dates = pd.bdate_range("2024-01-01", periods=3)
    market = pd.DataFrame(
        {"date": dates, "symbol": ["A"] * 3, "open": [100.0] * 3, "close": [100.0] * 3}
    )
    target = pd.DataFrame({"execution_date": [dates[0]], "symbol": ["A"], "weight": [1.0]})
    stop = pd.DataFrame({"execution_date": [dates[1]], "symbol": ["A"]})
    r = simulate_targets(
        market,
        pd.Series(10.0, index=dates),
        target,
        initial_capital=100000,
        apply_delivery_costs=True,
        forced_exit_signals=stop,
    )
    assert r.daily.loc[dates[1], "cost_stt"] == pytest.approx(
        r.daily.loc[dates[1], "sell_value"] * 0.001
    )
    assert r.daily.loc[dates[1], "buy_value"] == 0
    assert r.daily.loc[dates[1], "cash_value"] == pytest.approx(r.daily.loc[dates[1], "equity"])


def test_date_specific_stt_changes():
    a = delivery_trade_cost(1e6, 1.1e6, trade_date=pd.Timestamp("2007-01-01"))
    b = delivery_trade_cost(1e6, 1.1e6, trade_date=pd.Timestamp("2026-08-29"))
    assert a["stt"] == 2625
    assert b["stt"] == 2100


def test_jt_drift_gross_budgets_cap():
    current = pd.Series({"A": 0.45, "B": 0.1, "C": -0.15, "D": -0.3})
    selected = pd.Series({"A": 0.25, "B": 0.25, "C": -0.25, "D": -0.25})
    result = academic_winner_drift_target_weights(current, selected, 4)
    assert result[result > 0].sum() == pytest.approx(0.5)
    assert -result[result < 0].sum() == pytest.approx(0.5)
    assert result.abs().max() <= 0.5
