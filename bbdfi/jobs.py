from datetime import date, timedelta

from sqlalchemy.orm import Session

from bbdfi.marketdata import bhavcopy, sample
from bbdfi.marketdata.store import save_bars


def ingest_day(session: Session, day: date, universe: str = "nifty50") -> int:
    """Load one day's NSE Bhavcopy. Returns 0 when NSE has no file for that day."""
    if day.weekday() >= 5:
        return 0
    try:
        bars = bhavcopy.fetch_day(day, universe)
    except bhavcopy.NoDataForDate:
        return 0
    count = save_bars(session, bars, source="nse")
    session.commit()
    return count


def backfill(session: Session, days: int, universe: str = "nifty50", end: date | None = None) -> dict[str, int]:
    end = end or date.today()
    loaded = {}
    for offset in range(days, -1, -1):
        day = end - timedelta(days=offset)
        count = ingest_day(session, day, universe)
        if count:
            loaded[day.isoformat()] = count
    return loaded


def seed_sample(session: Session, days: int = 180) -> int:
    count = save_bars(session, sample.generate(days), source="sample")
    session.commit()
    return count
