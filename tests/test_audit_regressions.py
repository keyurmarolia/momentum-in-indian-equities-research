import numpy as np
import pandas as pd
import pytest

from momentum_india.comparison import comparison_metrics
from momentum_india.notebook_views import display_series
from momentum_india.portfolio import simulate_targets
from momentum_india.risk import align_cash_nav
from momentum_india.tax_ledger import annual_equity_tax, fifo_realizations
from scripts.build_notebook_diagnostics import add_churn


@pytest.mark.parametrize(
    "buy,sell,expected",
    [
        ("2017-12-01", "2018-06-01", 100),
        ("2016-12-01", "2018-03-01", 100),
        ("2016-12-01", "2018-06-01", 150),
    ],
)
def test_grandfathering_only_qualifying_long_term_disposals(buy, sell, expected):
    trades = pd.DataFrame(
        dict(
            date=pd.to_datetime([buy, sell]),
            symbol=["A", "A"],
            price=[100.0, 200.0],
            quantity_change=[1.0, -1.0],
        )
    )
    actual = fifo_realizations(trades, pd.Series({"A": 150.0})).iloc[0]
    assert actual.cost_basis == expected


def test_exempt_disposals_do_not_create_or_consume_tax_losses():
    realized = pd.DataFrame(
        dict(
            sale_date=pd.to_datetime(["2017-12-01", "2017-12-01", "2017-12-01", "2019-01-01"]),
            holding_class=["long_term", "long_term", "short_term", "short_term"],
            realized_gain=[-500.0, 1000.0, -100.0, 200.0],
            financial_year=["FY2017-18"] * 3 + ["FY2018-19"],
        )
    )
    taxes = annual_equity_tax(realized).set_index("financial_year")
    assert taxes.loc["FY2017-18", "long_term_loss_carryforward"] == 0
    assert taxes.loc["FY2017-18", "short_term_loss_carryforward"] == 100
    assert taxes.loc["FY2018-19", "short_term_taxable_gain"] == 100


def test_chart_downsampling_never_invents_future_friday():
    values = pd.Series(
        [1.0, 2.0, 3.0, 4.0],
        index=pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]),
    )
    shown = display_series(values)
    assert shown.index.isin(values.index).all()
    assert shown.index[-1] == values.index[-1]


def test_delisting_mark_is_not_automatically_a_tax_loss():
    trades = pd.DataFrame(
        dict(
            date=pd.to_datetime(["2022-01-01", "2024-01-01"]),
            symbol=["A", "A"],
            price=[100.0, 0.0],
            quantity_change=[1.0, -1.0],
            exit_reason=["scheduled_rebalance", "confirmed_delisting_zero_recovery"],
        )
    )
    realized = fifo_realizations(trades)
    assert realized.realized_gain.iloc[0] == -100
    assert not realized.taxable_disposal.iloc[0]
    assert annual_equity_tax(realized).empty


def test_comparison_uses_identical_window_and_initial_peak():
    dates = pd.bdate_range("2024-01-01", periods=5)
    frames = []
    for name, start in [("raw_momentum", 0), ("km_momentum", 2)]:
        frames.append(
            pd.DataFrame(
                dict(
                    date=dates[start:],
                    strategy=name,
                    formation_period="6M",
                    frequency="1M",
                    holdings_n=12,
                    maintenance="equal_weight",
                    return_type="post_tax",
                    **{"return": [-0.1] * len(dates[start:])},
                )
            )
        )
    result = comparison_metrics(pd.concat(frames), pd.Series(0.0, index=dates))
    assert result.start_date.eq(dates[2]).all()
    assert result.observations.eq(3).all()
    assert np.allclose(result.average_drawdown, np.mean([-0.1, -0.19, -0.271]))
    assert result.time_below_prior_peak.eq(1).all()


def test_comparison_rejects_missing_sessions():
    dates = pd.bdate_range("2024-01-01", periods=5)
    common = dict(
        formation_period="6M",
        frequency="1M",
        holdings_n=12,
        maintenance="equal_weight",
        return_type="post_tax",
    )
    frames = [
        pd.DataFrame(dict(date=dates, strategy="raw_momentum", **common, **{"return": 0.01})),
        pd.DataFrame(
            dict(date=dates.delete(2), strategy="km_momentum", **common, **{"return": 0.01})
        ),
    ]
    with pytest.raises(ValueError, match="identical complete"):
        comparison_metrics(pd.concat(frames), pd.Series(0.0, index=dates))


def test_cash_nav_cannot_be_backfilled_from_the_future():
    dates = pd.bdate_range("2024-01-01", periods=2)
    market = pd.DataFrame(dict(date=dates, symbol="A", open=100.0, close=100.0))
    targets = pd.DataFrame(dict(execution_date=[dates[0]], symbol=["A"], weight=[1.0]))
    with pytest.raises(ValueError, match="Cash NAV"):
        simulate_targets(market, pd.Series([10.0], index=dates[1:]), targets)


def test_missing_weekday_nav_uses_latest_known_weekend_value():
    nav = pd.Series(
        [100.0, 101.0, 102.0], index=pd.to_datetime(["2025-09-26", "2025-09-28", "2025-09-30"])
    )
    calendar = pd.to_datetime(["2025-09-26", "2025-09-29", "2025-09-30"])
    actual = align_cash_nav(nav, calendar)
    assert actual.tolist() == [100.0, 101.0, 102.0]
    assert actual.pct_change(fill_method=None).iloc[1] == pytest.approx(0.01)


def test_empty_rebalance_resets_membership_retention():
    dates = pd.date_range("2024-01-01", periods=3, freq="MS")
    events = pd.DataFrame(
        dict(
            strategy="km_momentum",
            formation_period="6M",
            frequency="1M",
            holdings_n=12,
            maintenance="equal_weight",
            signal_date=dates,
            execution_date=pd.DatetimeIndex([day + pd.DateOffset(days=1) for day in dates]),
        )
    )
    holdings = events.iloc[[0, 2]].assign(symbol="A")
    actual = add_churn(events, holdings)
    assert actual.entries.tolist() == [1, 0, 1]
    assert actual.exits.tolist() == [0, 1, 0]
    assert pd.isna(actual.name_retention_rate.iloc[2])
