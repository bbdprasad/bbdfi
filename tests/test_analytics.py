import pytest

from bbdfi.analytics import indicators as ind
from bbdfi.analytics.market import chart, describe, heatmap, movers
from bbdfi.commands import parse

SYMBOLS = {"NIFTY 50", "NIFTY BANK", "INFY", "INFY2", "RELIANCE", "M&M"}


def test_sma_ema_rsi():
    assert ind.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert ind.ema([1, 2, 3], 2)[1:] == [1.5, pytest.approx(2.5)]
    assert ind.rsi([1, 2, 3, 4, 5, 6], 3)[-1] == 100.0
    values = [44, 44.3, 44.1, 43.6, 44.3, 44.8, 45.1, 45.4, 45.8, 46.1, 45.9, 46.2, 45.6, 46.2, 46.3, 46.3]
    assert 60 < ind.rsi(values, 14)[-1] < 80
    upper, lower = ind.bollinger([10] * 25, 20)
    assert upper[-1] == lower[-1] == 10


def test_macd_lengths_and_drawdown():
    values = [100 + i for i in range(60)]
    line, signal, hist = ind.macd(values)
    assert len(line) == len(signal) == len(hist) == 60
    assert line[24] is None and line[25] is not None and signal[-1] is not None
    assert ind.max_drawdown([100, 120, 90, 130]) == 25.0


def test_beta_of_scaled_series_is_scale():
    market = [0.01, -0.02, 0.015, 0.0, 0.03, -0.01, 0.02, -0.005, 0.01, 0.012, -0.02]
    assert ind.beta([2 * r for r in market], market) == pytest.approx(2.0)


def test_command_parser():
    assert parse("reliance <GO>", SYMBOLS) == {"action": "security", "symbol": "RELIANCE", "view": "des"}
    assert parse("nifty", SYMBOLS)["symbol"] == "NIFTY 50"
    assert parse("banknifty gp", SYMBOLS) == {"action": "security", "symbol": "NIFTY BANK", "view": "chart"}
    assert parse("b 10 infy", SYMBOLS) == {"action": "order", "side": "BUY", "quantity": 10, "symbol": "INFY"}
    assert parse("SELL ALL M&M", SYMBOLS)["quantity"] is None
    assert parse("BUY ALL INFY", SYMBOLS)["action"] == "error"
    assert parse("mov", SYMBOLS) == {"action": "movers"}
    assert parse("help", SYMBOLS)["commands"]
    error = parse("INF", SYMBOLS)
    assert error["action"] == "error" and error["suggestions"] == ["INFY", "INFY2"]


def test_market_analytics(session, load):
    load("NIFTY 50", [100 + i for i in range(30)], kind="INDEX")
    load("INFY", [10 + i * 0.1 for i in range(29)] + [20])
    load("TCS", [50 - i * 0.1 for i in range(30)])
    board = movers(session)
    assert board["gainers"][0]["symbol"] == "INFY"
    assert board["losers"][0]["symbol"] == "TCS"
    assert board["breadth"]["advances"] == 1 and board["breadth"]["new_highs"] == 1
    sectors = {row["sector"]: row for row in heatmap(session)["sectors"]}
    assert {m["symbol"] for m in sectors["IT"]["members"]} == {"TCS", "INFY"}
    info = describe(session, "INFY")
    assert info["sector"] == "IT" and info["returns"]["1W"] > 0 and info["beta_1y"] is not None
    assert describe(session, "NOPE") is None
    series = chart(session, "INFY", 10, {"sma20", "rsi14", "bogus"})
    assert len(series["bars"]) == 10 and set(series["indicators"]) == {"sma20", "rsi14"}
    assert series["indicators"]["sma20"][-1] is not None
