from datetime import date

import pytest
from pydantic import ValidationError

from bbdfi.engine.fills import Rejected, fill
from bbdfi.engine.rules import parse_rule
from tests.conftest import make_bars


def as_view(**series):
    return {symbol: make_bars(symbol, closes) for symbol, closes in series.items()}


def test_prev_close_drop_triggers_buy():
    view = as_view(NIFTY=[100, 98], INFY=[10, 10])
    rule = parse_rule("prev_close_move", {"watch_symbol": "NIFTY", "direction": "down", "threshold_pct": 1.5,
                                          "trade_symbol": "INFY", "quantity": 5})
    day = view["NIFTY"][-1].date
    [signal] = rule.evaluate(view, day, 0)
    assert (signal.symbol, signal.side, signal.quantity) == ("INFY", "BUY", 5)
    assert rule.evaluate(as_view(NIFTY=[100, 99], INFY=[10, 10]), day, 0) == []


def test_prev_close_ignores_stale_day():
    view = as_view(NIFTY=[100, 90], INFY=[10, 10])
    rule = parse_rule("prev_close_move", {"watch_symbol": "NIFTY", "threshold_pct": 1, "trade_symbol": "INFY", "quantity": 1})
    assert rule.evaluate(view, date(2030, 1, 1), 0) == []


def test_sma_cross_buys_on_cross_up_and_sells_on_cross_down():
    rule = parse_rule("sma_cross", {"symbol": "X", "period": 3, "quantity": 2})
    up = as_view(X=[10, 10, 10, 9, 12])
    assert rule.evaluate(up, up["X"][-1].date, 0)[0].side == "BUY"
    down = as_view(X=[10, 10, 10, 12, 8])
    [signal] = rule.evaluate(down, down["X"][-1].date, 2)
    assert (signal.side, signal.quantity) == ("SELL", None)
    assert rule.evaluate(down, down["X"][-1].date, 0) == []


def test_take_profit_and_stop_loss():
    rule = parse_rule("take_profit_stop_loss", {"symbol": "X", "take_profit_pct": 10, "stop_loss_pct": 5})
    view = as_view(X=[100, 111])
    assert rule.evaluate(view, view["X"][-1].date, 3, 100)[0].reason.startswith("Take profit")
    view = as_view(X=[100, 94])
    assert rule.evaluate(view, view["X"][-1].date, 3, 100)[0].reason.startswith("Stop loss")
    with pytest.raises(ValidationError):
        parse_rule("take_profit_stop_loss", {"symbol": "X"})


def test_fill_rules():
    result = fill(1000, 0, 0, "BUY", 5, 100)
    assert (result.cash, result.held, result.average_price) == (500, 5, 100)
    result = fill(500, 5, 100, "BUY", 5, 80)
    assert result.average_price == 90
    assert fill(500, 5, 100, "SELL", None, 120).cash == 1100
    with pytest.raises(Rejected):
        fill(100, 0, 0, "BUY", 5, 100)
    with pytest.raises(Rejected):
        fill(100, 2, 10, "SELL", 3, 10)
