"""Paper broker: applies orders to a profile's stored cash and positions."""

from datetime import date

from sqlalchemy.orm import Session

from bbdfi.engine.fills import Rejected, fill
from bbdfi.models import Order, Position, Profile


def place_order(
    session: Session,
    profile: Profile,
    symbol: str,
    side: str,
    quantity: int | None,
    price: float,
    trade_date: date,
    source: str = "manual",
    strategy_id: str | None = None,
    note: str = "",
    record_rejection: bool = False,
) -> Order:
    """Fill a paper order. Raises Rejected, or records a rejected order when record_rejection is set."""
    position = session.get(Position, (profile.id, symbol))
    held = position.quantity if position else 0
    average = position.average_price if position else 0.0
    try:
        result = fill(profile.cash, held, average, side, quantity, price)
    except Rejected as error:
        if not record_rejection:
            raise
        order = Order(profile_id=profile.id, strategy_id=strategy_id, symbol=symbol, side=side,
                      quantity=quantity or held, price=price, status="rejected", source=source,
                      note=f"{note}. {error}" if note else str(error), trade_date=trade_date)
        session.add(order)
        return order

    profile.cash = result.cash
    if result.held:
        if position is None:
            position = Position(profile_id=profile.id, symbol=symbol)
            session.add(position)
        position.quantity = result.held
        position.average_price = result.average_price
    elif position is not None:
        session.delete(position)

    order = Order(profile_id=profile.id, strategy_id=strategy_id, symbol=symbol, side=side,
                  quantity=result.quantity, price=price, status="filled", source=source,
                  note=note, trade_date=trade_date)
    session.add(order)
    session.flush()
    return order
