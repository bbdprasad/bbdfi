"""Daily engine: after each day's prices land, run every active strategy and snapshot equity."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bbdfi.engine.broker import place_order
from bbdfi.engine.rules import evaluate, parse_rule
from bbdfi.marketdata.store import closes_on, history, latest_date, trading_days
from bbdfi.models import EquitySnapshot, Position, Profile, Strategy

MAX_CATCH_UP_DAYS = 30


@dataclass
class DaySummary:
    day: date
    strategies_run: int = 0
    filled: int = 0
    rejected: int = 0
    snapshots: int = 0
    errors: list[str] = field(default_factory=list)


def _positions(session: Session, profile_id: str) -> dict[str, tuple[int, float]]:
    rows = session.scalars(select(Position).where(Position.profile_id == profile_id))
    return {row.symbol: (row.quantity, row.average_price) for row in rows}


def snapshot_equity(session: Session, day: date) -> int:
    closes = closes_on(session, day)
    count = 0
    for profile in session.scalars(select(Profile)):
        if profile.created_at and profile.created_at.date() > day:
            continue
        holdings = sum(qty * closes.get(symbol, avg) for symbol, (qty, avg) in _positions(session, profile.id).items())
        session.merge(EquitySnapshot(profile_id=profile.id, date=day, equity=round(profile.cash + holdings, 2)))
        count += 1
    return count


def run_day(session: Session, day: date) -> DaySummary:
    summary = DaySummary(day)
    strategies = [
        strategy for strategy in session.scalars(select(Strategy).where(Strategy.active.is_(True)).order_by(Strategy.created_at))
        if (strategy.last_run_date is None or strategy.last_run_date < day)
        and (strategy.start_after is None or strategy.start_after < day)
    ]
    parsed = []
    for strategy in strategies:
        try:
            parsed.append((strategy, parse_rule(strategy.rule_type, strategy.params)))
        except ValueError as error:
            summary.errors.append(f"{strategy.id}: {error}")
    symbols = set().union(*(rule.symbols for _, rule in parsed)) if parsed else set()
    lookback = max((rule.lookback for _, rule in parsed), default=1)
    bars = history(session, symbols, day, lookback + 1)

    for strategy, rule in parsed:
        profile = session.get(Profile, strategy.profile_id)
        for signal in evaluate(rule, bars, day, _positions(session, profile.id)):
            price_bar = (bars.get(signal.symbol) or [None])[-1]
            order = place_order(
                session, profile, signal.symbol, signal.side, signal.quantity,
                price_bar.close if price_bar else 0, day, source="strategy",
                strategy_id=strategy.id, note=f"{strategy.name}: {signal.reason}", record_rejection=True,
            )
            if order.status == "filled":
                summary.filled += 1
            else:
                summary.rejected += 1
        strategy.last_run_date = day
        summary.strategies_run += 1

    session.flush()
    summary.snapshots = snapshot_equity(session, day)
    return summary


def run_pending(session: Session, until: date | None = None) -> list[DaySummary]:
    """Run every market day that has data but has not been processed yet (idempotent)."""
    until = until or latest_date(session)
    if until is None:
        return []
    markers = [session.scalar(select(func.max(EquitySnapshot.date)))]
    for strategy in session.scalars(select(Strategy).where(Strategy.active.is_(True))):
        marker = max(filter(None, [strategy.last_run_date, strategy.start_after]), default=None)
        markers.append(marker)
    markers = [marker for marker in markers if marker is not None]
    days = trading_days(session, after=min(markers), until=until) if markers else [until]
    days = days[-MAX_CATCH_UP_DAYS:] or [until]
    summaries = [run_day(session, day) for day in days]
    session.commit()
    return summaries
