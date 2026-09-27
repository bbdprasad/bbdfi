"""Market-wide analytics: movers, breadth, sector heatmap, security description, chart series."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from bbdfi.analytics import indicators as ind
from bbdfi.marketdata.store import history, latest_date
from bbdfi.marketdata.universe import SECTORS, sector_of
from bbdfi.models import DailyBar, Instrument

YEAR = 250
BENCHMARK = "NIFTY 50"


def _change(bar: DailyBar) -> float:
    return round((bar.close / bar.prev_close - 1) * 100, 2) if bar.prev_close else 0.0


def _kinds(session: Session) -> dict[str, Instrument]:
    return {instrument.symbol: instrument for instrument in session.scalars(select(Instrument))}


def movers(session: Session, count: int = 10) -> dict:
    day = latest_date(session)
    if day is None:
        return {"as_of": None, "gainers": [], "losers": [], "active": [], "breadth": {}}
    instruments = _kinds(session)
    equities = [symbol for symbol, instrument in instruments.items() if instrument.kind == "EQ"]
    bars = history(session, equities, day, YEAR)
    rows, highs, lows = [], 0, 0
    for symbol, series in bars.items():
        last = series[-1]
        if last.date != day:
            continue
        year_high = max(bar.high for bar in series)
        year_low = min(bar.low for bar in series)
        highs += last.high >= year_high
        lows += last.low <= year_low
        rows.append({
            "symbol": symbol, "name": instruments[symbol].name, "sector": sector_of(symbol),
            "close": last.close, "change_pct": _change(last), "volume": last.volume,
            "value_cr": round(last.close * last.volume / 1e7, 2),
        })
    advances = sum(row["change_pct"] > 0 for row in rows)
    declines = sum(row["change_pct"] < 0 for row in rows)
    by_change = sorted(rows, key=lambda row: row["change_pct"], reverse=True)
    return {
        "as_of": day.isoformat(),
        "gainers": [row for row in by_change if row["change_pct"] > 0][:count],
        "losers": [row for row in reversed(by_change) if row["change_pct"] < 0][:count],
        "active": sorted(rows, key=lambda row: row["value_cr"], reverse=True)[:count],
        "breadth": {"advances": advances, "declines": declines, "unchanged": len(rows) - advances - declines,
                    "new_highs": highs, "new_lows": lows, "total": len(rows)},
    }


def heatmap(session: Session) -> dict:
    day = latest_date(session)
    if day is None:
        return {"as_of": None, "sectors": []}
    rows = session.scalars(select(DailyBar).where(DailyBar.date == day))
    by_symbol = {bar.symbol: bar for bar in rows}
    sectors = []
    for sector, symbols in SECTORS.items():
        members = []
        for symbol in symbols:
            bar = by_symbol.get(symbol)
            if bar:
                members.append({"symbol": symbol, "change_pct": _change(bar), "close": bar.close,
                                "value_cr": round(bar.close * bar.volume / 1e7, 2)})
        if not members:
            continue
        weight = sum(member["value_cr"] for member in members)
        change = (sum(m["change_pct"] * m["value_cr"] for m in members) / weight if weight
                  else sum(m["change_pct"] for m in members) / len(members))
        members.sort(key=lambda member: member["value_cr"], reverse=True)
        sectors.append({"sector": sector, "change_pct": round(change, 2), "value_cr": round(weight, 2), "members": members})
    sectors.sort(key=lambda sector: sector["value_cr"], reverse=True)
    return {"as_of": day.isoformat(), "sectors": sectors}


def _return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days:
        return None
    return round((closes[-1] / closes[-1 - days] - 1) * 100, 2)


def _last(series: list) -> float | None:
    return round(series[-1], 2) if series and series[-1] is not None else None


def describe(session: Session, symbol: str) -> dict | None:
    instrument = session.get(Instrument, symbol)
    day = latest_date(session)
    if instrument is None or day is None:
        return None
    bars = history(session, {symbol, BENCHMARK}, day, YEAR + 1)
    series = bars.get(symbol) or []
    if not series:
        return None
    last = series[-1]
    closes = [bar.close for bar in series]
    returns = ind.daily_returns(closes)
    benchmark = bars.get(BENCHMARK) or []
    beta_value = None
    if symbol != BENCHMARK and benchmark:
        market_by_date = {bar.date: bar.close for bar in benchmark}
        paired = [(bar.close, market_by_date[bar.date]) for bar in series if bar.date in market_by_date]
        beta_value = ind.beta(ind.daily_returns([a for a, _ in paired]), ind.daily_returns([m for _, m in paired]))
    moving = {period: _last(ind.sma(closes, period)) for period in (20, 50, 200)}
    volumes = [bar.volume for bar in series[-20:]]
    return {
        "symbol": symbol, "name": instrument.name, "kind": instrument.kind, "sector": sector_of(symbol),
        "date": last.date.isoformat(), "close": last.close, "prev_close": last.prev_close, "change_pct": _change(last),
        "open": last.open, "high": last.high, "low": last.low, "volume": last.volume,
        "year_high": max(bar.high for bar in series[-YEAR:]), "year_low": min(bar.low for bar in series[-YEAR:]),
        "avg_volume_20d": round(sum(volumes) / len(volumes)) if volumes else 0,
        "returns": {label: _return(closes, days) for label, days in
                    (("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("1Y", YEAR))},
        "volatility_20d": _round(ind.annualized_volatility(returns[-20:])),
        "volatility_1y": _round(ind.annualized_volatility(returns[-YEAR:])),
        "beta_1y": _round(beta_value),
        "rsi_14": _last(ind.rsi(closes, 14)),
        "sma": moving,
        "vs_sma": {period: round((last.close / value - 1) * 100, 2) if value else None for period, value in moving.items()},
        "history_days": len(series),
    }


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


INDICATORS = {"sma20", "sma50", "sma200", "ema20", "ema50", "bb20", "rsi14", "macd"}
WARMUP = 200


def chart(session: Session, symbol: str, days: int, wanted: set[str]) -> dict | None:
    bars = list(reversed(list(session.scalars(
        select(DailyBar).where(DailyBar.symbol == symbol).order_by(DailyBar.date.desc()).limit(days + WARMUP)))))
    if not bars:
        return None
    closes = [bar.close for bar in bars]
    series: dict[str, list] = {}
    for name in wanted & INDICATORS:
        if name.startswith("sma"):
            series[name] = ind.sma(closes, int(name[3:]))
        elif name.startswith("ema"):
            series[name] = ind.ema(closes, int(name[3:]))
        elif name == "bb20":
            series["bb20_upper"], series["bb20_lower"] = ind.bollinger(closes, 20)
        elif name == "rsi14":
            series[name] = ind.rsi(closes, 14)
        elif name == "macd":
            series["macd"], series["macd_signal"], series["macd_hist"] = ind.macd(closes)
    start = max(0, len(bars) - days)
    return {
        "symbol": symbol,
        "bars": [{"date": bar.date.isoformat(), "open": bar.open, "high": bar.high, "low": bar.low,
                  "close": bar.close, "volume": bar.volume} for bar in bars[start:]],
        "indicators": {name: [_round(v) for v in values[start:]] for name, values in series.items()},
    }
