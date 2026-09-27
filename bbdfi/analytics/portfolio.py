"""Risk and performance analytics for one paper account."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from bbdfi.analytics import indicators as ind
from bbdfi.marketdata.store import closes_on, latest_date
from bbdfi.marketdata.universe import sector_of
from bbdfi.models import DailyBar, EquitySnapshot, Order, Position, Profile

RISK_FREE_RATE = 6.5  # % a year, roughly the Indian 91-day T-bill yield


def _realized(orders: list[Order]) -> dict:
    """Replay filled orders at average cost to get realized P&L per closing trade."""
    book: dict[str, tuple[int, float]] = {}
    closed = []
    for order in orders:
        held, average = book.get(order.symbol, (0, 0.0))
        if order.side == "BUY":
            total = held + order.quantity
            book[order.symbol] = (total, (held * average + order.quantity * order.price) / total)
        else:
            closed.append((order.symbol, order.quantity * (order.price - average)))
            remaining = held - order.quantity
            book[order.symbol] = (remaining, average if remaining else 0.0)
    wins = [pnl for _, pnl in closed if pnl > 0]
    losses = [pnl for _, pnl in closed if pnl < 0]
    return {
        "realized_pnl": round(sum(pnl for _, pnl in closed), 2),
        "closed_trades": len(closed),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
    }


def analytics(session: Session, profile: Profile) -> dict:
    day = latest_date(session)
    closes = closes_on(session, day) if day else {}
    positions = list(session.scalars(select(Position).where(Position.profile_id == profile.id)))
    holdings = [(p, p.quantity * closes.get(p.symbol, p.average_price)) for p in positions]
    invested = sum(value for _, value in holdings)
    equity = profile.cash + invested

    exposure: dict[str, float] = {}
    for position, value in holdings:
        sector = sector_of(position.symbol)
        exposure[sector] = exposure.get(sector, 0) + value
    sectors = sorted(({"sector": sector, "value": round(value, 2), "weight_pct": round(value / equity * 100, 2)}
                      for sector, value in exposure.items()), key=lambda row: row["value"], reverse=True)

    snapshots = list(session.scalars(select(EquitySnapshot).where(EquitySnapshot.profile_id == profile.id)
                                     .order_by(EquitySnapshot.date)))
    curve = [s.equity for s in snapshots]
    returns = ind.daily_returns(curve)
    volatility = ind.annualized_volatility(returns)
    sharpe = None
    if volatility and len(returns) >= 5:
        annual_return = (sum(returns) / len(returns)) * 252 * 100
        sharpe = round((annual_return - RISK_FREE_RATE) / volatility, 2)
    market_beta = None
    if len(snapshots) >= 11:
        dates = [s.date for s in snapshots]
        market = dict(session.execute(select(DailyBar.date, DailyBar.close).where(
            DailyBar.symbol == "NIFTY 50", DailyBar.date.in_(dates))).all())
        paired = [(s.equity, market[s.date]) for s in snapshots if s.date in market]
        market_beta = ind.beta(ind.daily_returns([a for a, _ in paired]), ind.daily_returns([m for _, m in paired]))

    orders = list(session.scalars(select(Order).where(Order.profile_id == profile.id, Order.status == "filled")
                                  .order_by(Order.created_at)))
    contributors = sorted(({"symbol": p.symbol, "pnl": round(value - p.quantity * p.average_price, 2)}
                           for p, value in holdings), key=lambda row: row["pnl"], reverse=True)
    return {
        "as_of": day.isoformat() if day else None,
        "equity": round(equity, 2),
        "cash_pct": round(profile.cash / equity * 100, 2) if equity else 100.0,
        "invested_pct": round(invested / equity * 100, 2) if equity else 0.0,
        "positions": len(positions),
        "largest_position_pct": round(max((v for _, v in holdings), default=0) / equity * 100, 2) if equity else 0.0,
        "sectors": sectors,
        "volatility_pct": round(volatility, 2) if volatility is not None else None,
        "sharpe": sharpe,
        "max_drawdown_pct": round(ind.max_drawdown(curve), 2) if curve else None,
        "beta": round(market_beta, 2) if market_beta is not None else None,
        "days_tracked": len(snapshots),
        "contributors": contributors,
        **_realized(orders),
    }
