"""Public leaderboard: paper return over the last 7 calendar days."""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bbdfi.marketdata.store import closes_on, latest_date
from bbdfi.models import EquitySnapshot, Order, Position, Profile

WINDOW_DAYS = 7


def leaderboard(session: Session, limit: int = 50) -> dict:
    """Ranks everyone who has placed at least one paper order.

    Current equity is valued live at the latest close, so a trade shows up straight away. The
    base is equity at the start of the window; traders who joined inside it start from their
    starting cash.
    """
    latest = latest_date(session)
    if latest is None:
        return {"as_of": None, "window_days": WINDOW_DAYS, "entries": []}
    window_start = latest - timedelta(days=WINDOW_DAYS)
    since = datetime.combine(window_start, time.min, tzinfo=timezone.utc)
    closes = closes_on(session, latest)
    holdings: dict[str, float] = {}
    for position in session.scalars(select(Position)):
        holdings[position.profile_id] = holdings.get(position.profile_id, 0) + position.quantity * closes.get(position.symbol, position.average_price)
    trades_in_window = dict(session.execute(
        select(Order.profile_id, func.count()).where(Order.status == "filled", Order.trade_date > window_start)
        .group_by(Order.profile_id)
    ).all())
    traders = set(session.scalars(select(Order.profile_id).where(Order.status == "filled").distinct()))

    entries = []
    for profile in session.scalars(select(Profile).where(Profile.id.in_(traders))):
        equity = profile.cash + holdings.get(profile.id, 0)
        base = session.scalar(
            select(EquitySnapshot.equity)
            .where(EquitySnapshot.profile_id == profile.id, EquitySnapshot.date <= window_start)
            .order_by(EquitySnapshot.date.desc()).limit(1)
        ) or profile.starting_cash
        created = profile.created_at.replace(tzinfo=profile.created_at.tzinfo or timezone.utc) if profile.created_at else None
        entries.append({
            "handle": profile.handle,
            "display_name": profile.display_name,
            "return_pct": round((equity / base - 1) * 100, 2),
            "equity": round(equity, 2),
            "trades": trades_in_window.get(profile.id, 0),
            "new": bool(created and created > since),
        })
    entries.sort(key=lambda entry: (-entry["return_pct"], -entry["trades"], entry["handle"]))
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank
    return {"as_of": latest.isoformat(), "window_days": WINDOW_DAYS, "entries": entries[:limit]}
