"""Deterministic sample prices so the app works before real NSE data is loaded.

Bars are stored with source="sample" and the UI labels them as sample data.
"""

import random
from datetime import date, timedelta

from bbdfi.marketdata.bhavcopy import Bar
from bbdfi.marketdata.universe import INDICES, NIFTY50

START_PRICES = {
    "NIFTY 50": 24800.0, "NIFTY BANK": 55200.0, "RELIANCE": 1380.0, "HDFCBANK": 950.0,
    "ICICIBANK": 1400.0, "INFY": 1500.0, "TCS": 3150.0, "SBIN": 810.0, "ITC": 410.0,
    "LT": 3600.0, "BHARTIARTL": 1900.0, "KOTAKBANK": 2000.0, "AXISBANK": 1150.0, "MARUTI": 14500.0,
}


def weekdays_back(end: date, count: int) -> list[date]:
    days = []
    day = end
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def generate(days: int = 180, end: date | None = None) -> list[Bar]:
    end = end or date.today()
    calendar = weekdays_back(end, days)
    bars: list[Bar] = []
    symbols = [(symbol, name, "INDEX") for symbol, name in INDICES.items()] + [(s, s, "EQ") for s in NIFTY50]
    for symbol, name, kind in symbols:
        rng = random.Random(symbol)
        price = START_PRICES.get(symbol) or rng.uniform(200, 3000)
        volatility = 0.009 if kind == "INDEX" else 0.016
        for day in calendar:
            prev_close = price
            move = rng.gauss(0.0004, volatility)
            open_ = prev_close * (1 + rng.gauss(0, volatility / 3))
            price = round(prev_close * (1 + move), 2)
            high = round(max(open_, price) * (1 + abs(rng.gauss(0, volatility / 2))), 2)
            low = round(min(open_, price) * (1 - abs(rng.gauss(0, volatility / 2))), 2)
            bars.append(Bar(symbol, name, kind, day, round(open_, 2), high, low, price, round(prev_close, 2),
                            0 if kind == "INDEX" else rng.randint(100_000, 5_000_000)))
    return bars
