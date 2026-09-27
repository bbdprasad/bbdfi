from dataclasses import dataclass


class Rejected(Exception):
    pass


@dataclass
class Fill:
    quantity: int
    cash: float
    held: int
    average_price: float


def fill(cash: float, held: int, average_price: float, side: str, quantity: int | None, price: float) -> Fill:
    """Apply a paper order at `price`. Long only: sells are capped by what is held.

    quantity=None on a SELL closes the whole position.
    """
    if price <= 0:
        raise Rejected("No price available")
    if side == "BUY":
        if not quantity or quantity < 1:
            raise Rejected("Quantity must be at least 1")
        cost = quantity * price
        if cost > cash + 1e-6:
            raise Rejected("Not enough paper cash")
        new_held = held + quantity
        return Fill(quantity, cash - cost, new_held, (held * average_price + cost) / new_held)
    if side == "SELL":
        if held <= 0:
            raise Rejected("No position to sell")
        quantity = held if quantity is None else quantity
        if quantity < 1:
            raise Rejected("Quantity must be at least 1")
        if quantity > held:
            raise Rejected(f"Only {held} held")
        new_held = held - quantity
        return Fill(quantity, cash + quantity * price, new_held, average_price if new_held else 0.0)
    raise Rejected(f"Unknown side {side}")
