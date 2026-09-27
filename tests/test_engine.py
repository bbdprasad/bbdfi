from datetime import timedelta

from sqlalchemy import select

from bbdfi.engine.backtest import backtest
from bbdfi.engine.rules import parse_rule
from bbdfi.engine.runner import run_pending
from bbdfi.leaderboard import leaderboard
from bbdfi.models import EquitySnapshot, Order, Profile, Strategy


def add_profile(session, pid, cash=100_000):
    from datetime import datetime, timezone
    profile = Profile(id=pid, handle=pid, display_name=pid, cash=cash, starting_cash=cash,
                      created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    session.add(profile)
    session.commit()
    return profile


def test_runner_trades_once_per_day_and_snapshots(session, load):
    bars = load("NIFTY 50", [100, 100, 97, 100, 96], kind="INDEX")
    load("INFY", [10, 10, 10, 10, 12])
    profile = add_profile(session, "asha")
    session.add(Strategy(profile_id="asha", name="Dip", rule_type="prev_close_move", start_after=bars[1].date,
                         params={"watch_symbol": "NIFTY 50", "direction": "down", "threshold_pct": 2,
                                 "trade_symbol": "INFY", "side": "BUY", "quantity": 100}))
    session.commit()

    run_pending(session)
    run_pending(session)  # idempotent

    orders = list(session.scalars(select(Order).order_by(Order.trade_date)))
    assert [(o.trade_date, o.price, o.status) for o in orders] == [(bars[2].date, 10, "filled"), (bars[4].date, 12, "filled")]
    session.refresh(profile)
    assert profile.cash == 100_000 - 1000 - 1200
    snapshots = list(session.scalars(select(EquitySnapshot).order_by(EquitySnapshot.date)))
    assert snapshots[-1].date == bars[4].date
    assert snapshots[-1].equity == 100_000 - 2200 + 200 * 12


def test_strategy_does_not_act_on_data_before_creation(session, load):
    bars = load("X", [10, 10, 9, 12, 13])
    add_profile(session, "ravi")
    session.add(Strategy(profile_id="ravi", name="Cross", rule_type="sma_cross", start_after=bars[-1].date,
                         params={"symbol": "X", "period": 2, "quantity": 1}))
    session.commit()
    run_pending(session)
    assert session.scalars(select(Order)).first() is None


def test_backtest_reports_trades_and_return(session, load):
    load("X", [10, 10, 10, 9, 12, 13, 14, 11, 10])
    result = backtest(session, parse_rule("sma_cross", {"symbol": "X", "period": 3, "quantity": 100}), days=6, cash=10_000)
    assert [t["side"] for t in result["trades"]] == ["BUY", "SELL"]
    assert result["trades"][0]["price"] == 12
    assert result["return_pct"] == round((10_000 - 1200 + 1100) / 10_000 * 100 - 100, 2)
    assert len(result["equity_curve"]) == 6


def test_leaderboard_ranks_seven_day_return(session, load):
    bars = load("X", [10] * 10)
    latest = bars[-1].date
    for pid, cash in (("a_one", 105_000), ("b_two", 60_000), ("idle", 100_000)):
        add_profile(session, pid, cash)
    session.add_all([
        EquitySnapshot(profile_id="a_one", date=latest - timedelta(days=8), equity=100_000),
        EquitySnapshot(profile_id="b_two", date=latest - timedelta(days=8), equity=50_000),
        Order(profile_id="a_one", symbol="X", side="BUY", quantity=1, price=10, status="filled", source="manual", trade_date=latest),
        Order(profile_id="b_two", symbol="X", side="BUY", quantity=1, price=10, status="filled", source="manual",
              trade_date=latest - timedelta(days=9)),
    ])
    session.commit()
    board = leaderboard(session)
    assert [(e["handle"], e["return_pct"], e["rank"], e["trades"]) for e in board["entries"]] == [
        ("b_two", 20.0, 1, 0), ("a_one", 5.0, 2, 1)]
