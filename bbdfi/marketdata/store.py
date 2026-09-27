from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bbdfi.marketdata.bhavcopy import Bar
from bbdfi.models import DailyBar, Instrument


def save_bars(session: Session, bars: list[Bar], source: str = "nse") -> int:
    known = set(session.scalars(select(Instrument.symbol)))
    for bar in bars:
        if bar.symbol not in known:
            session.add(Instrument(symbol=bar.symbol, name=bar.name, kind=bar.kind))
            known.add(bar.symbol)
        session.merge(DailyBar(
            symbol=bar.symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low,
            close=bar.close, prev_close=bar.prev_close, volume=bar.volume, source=source,
        ))
    session.flush()
    return len(bars)


def latest_date(session: Session) -> date | None:
    return session.scalar(select(func.max(DailyBar.date)))


def trading_days(session: Session, after: date | None = None, until: date | None = None) -> list[date]:
    query = select(DailyBar.date).distinct().order_by(DailyBar.date)
    if after:
        query = query.where(DailyBar.date > after)
    if until:
        query = query.where(DailyBar.date <= until)
    return list(session.scalars(query))


def closes_on(session: Session, day: date) -> dict[str, float]:
    """Latest close for every symbol as of `day` (carries forward symbols missing that day)."""
    latest = (
        select(DailyBar.symbol, func.max(DailyBar.date).label("d"))
        .where(DailyBar.date <= day)
        .group_by(DailyBar.symbol)
        .subquery()
    )
    rows = session.execute(
        select(DailyBar.symbol, DailyBar.close)
        .join(latest, (DailyBar.symbol == latest.c.symbol) & (DailyBar.date == latest.c.d))
    )
    return {symbol: close for symbol, close in rows}


def history(session: Session, symbols: set[str] | list[str], until: date, limit: int) -> dict[str, list[DailyBar]]:
    """The last `limit` bars on or before `until` for each symbol, oldest first."""
    if not symbols:
        return {}
    days = list(session.scalars(
        select(DailyBar.date).distinct().where(DailyBar.date <= until).order_by(DailyBar.date.desc()).limit(limit)
    ))
    if not days:
        return {}
    rows = session.scalars(
        select(DailyBar)
        .where(DailyBar.symbol.in_(list(symbols)), DailyBar.date >= min(days), DailyBar.date <= until)
        .order_by(DailyBar.date)
    )
    result: dict[str, list[DailyBar]] = defaultdict(list)
    for row in rows:
        result[row.symbol].append(row)
    return dict(result)
