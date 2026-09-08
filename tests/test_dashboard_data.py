import pandas as pd
import pytest

from momentum_india.costs import delivery_trade_cost
from momentum_india.dashboard_data import allocate_trade_fees, position_history


def trade(day, price, qty, fee=0):
    return dict(
        date=day, price=price, quantity_change=qty, fee=fee, exit_reason="scheduled_rebalance"
    )


def test_episode_add_trim_and_full_exit():
    h = position_history(
        [
            trade("2020-01-01", 100, 10, 2),
            trade("2020-02-01", 120, 5, 1),
            trade("2020-03-01", 130, -8, 2),
            trade("2020-04-01", 140, -7, 2),
        ],
        140,
        "2020-04-01",
    )
    assert [t["kind"] for t in h["trades"]] == ["entry", "add", "trim", "exit"]
    assert len(h["episodes"]) == 1
    e = h["episodes"][0]
    assert e["pnl"] == pytest.approx(413)
    assert e["realized"] == pytest.approx(413)
    assert e["unrealized"] == pytest.approx(0)
    assert e["price_change"] == pytest.approx(0.4)


def test_open_episode_and_reentry():
    h = position_history(
        [trade("2020-01-01", 100, 10), trade("2020-02-01", 90, -10), trade("2020-03-01", 80, 5, 2)],
        100,
        "2020-04-01",
    )
    assert len(h["episodes"]) == 2
    assert h["episodes"][1]["exit"] is None
    assert h["episodes"][1]["pnl"] == pytest.approx(98)


def test_short_reversal_splits_episodes():
    h = position_history(
        [trade("2020-01-01", 100, -10), trade("2020-02-01", 80, 15, 3)], 90, "2020-03-01"
    )
    assert [t["kind"] for t in h["trades"]] == ["entry", "exit", "entry"]
    assert h["episodes"][0]["pnl"] == pytest.approx(198)
    assert h["episodes"][1]["pnl"] == pytest.approx(49)
    assert sum(e["fees"] for e in h["episodes"]) == pytest.approx(3)


@pytest.mark.parametrize("date", ["2007-05-03", "2026-08-28"])
def test_allocated_fee_reconciles(date):
    values = [1000000.0, 1100000.0, -700000.0, -3000.0]
    t = pd.DataFrame(dict(date=[date] * 4, trade_value=values))
    actual = allocate_trade_fees(t).sum()
    expected = delivery_trade_cost(
        2100000, 703000, 2, 2, 2, [1000000, 1100000], [700000, 3000], trade_date=pd.Timestamp(date)
    )["total"]
    assert actual == pytest.approx(expected)
