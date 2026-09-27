"""Strategy rules. Each rule looks at end-of-day bars and emits paper order signals.

Rules are pure functions of price history and the current position, so the same code drives
the daily engine and the backtest preview.
"""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field, TypeAdapter, model_validator


class BarLike(Protocol):
    date: date
    close: float
    prev_close: float


@dataclass
class Signal:
    symbol: str
    side: str  # BUY or SELL
    quantity: int | None  # None means the whole position
    reason: str


class PrevCloseMove(BaseModel):
    """If <watch_symbol> closes X% below/above yesterday's close, buy/sell <trade_symbol>."""

    type: Literal["prev_close_move"] = "prev_close_move"
    watch_symbol: str
    direction: Literal["down", "up"] = "down"
    threshold_pct: float = Field(gt=0, le=20)
    trade_symbol: str
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: int = Field(ge=1, le=100_000)

    @property
    def symbols(self) -> set[str]:
        return {self.watch_symbol, self.trade_symbol}

    @property
    def lookback(self) -> int:
        return 1

    def describe(self) -> str:
        word = "drops" if self.direction == "down" else "rises"
        return (f"If {self.watch_symbol} {word} {self.threshold_pct:g}% vs yesterday's close, "
                f"{self.side.lower()} {self.quantity} {self.trade_symbol}.")

    def evaluate(self, bars: dict[str, list[BarLike]], day: date, held: int) -> list[Signal]:
        watch = bars.get(self.watch_symbol) or []
        trade = bars.get(self.trade_symbol) or []
        if not watch or watch[-1].date != day or not trade or trade[-1].date != day:
            return []
        bar = watch[-1]
        move = (bar.close / bar.prev_close - 1) * 100 if bar.prev_close else 0
        hit = move <= -self.threshold_pct if self.direction == "down" else move >= self.threshold_pct
        if not hit:
            return []
        return [Signal(self.trade_symbol, self.side, self.quantity, f"{self.watch_symbol} moved {move:+.2f}%")]


class SmaCross(BaseModel):
    """Buy when the close crosses above its N-day average; sell the position when it crosses below."""

    type: Literal["sma_cross"] = "sma_cross"
    symbol: str
    period: int = Field(ge=2, le=200)
    quantity: int = Field(ge=1, le=100_000)

    @property
    def symbols(self) -> set[str]:
        return {self.symbol}

    @property
    def lookback(self) -> int:
        return self.period + 1

    def describe(self) -> str:
        return (f"Buy {self.quantity} {self.symbol} when it closes above its {self.period}-day average; "
                f"sell when it closes below.")

    def evaluate(self, bars: dict[str, list[BarLike]], day: date, held: int) -> list[Signal]:
        series = bars.get(self.symbol) or []
        if len(series) < self.period + 1 or series[-1].date != day:
            return []
        closes = [bar.close for bar in series[-(self.period + 1):]]
        today_avg = sum(closes[1:]) / self.period
        yesterday_avg = sum(closes[:-1]) / self.period
        above_now, above_before = closes[-1] > today_avg, closes[-2] > yesterday_avg
        if above_now and not above_before:
            return [Signal(self.symbol, "BUY", self.quantity, f"Closed above {self.period}-day average")]
        if above_before and not above_now and held > 0:
            return [Signal(self.symbol, "SELL", None, f"Closed below {self.period}-day average")]
        return []


class TakeProfitStopLoss(BaseModel):
    """Exit the whole position once it is up X% or down Y% from the average buy price."""

    type: Literal["take_profit_stop_loss"] = "take_profit_stop_loss"
    symbol: str
    take_profit_pct: float | None = Field(default=None, gt=0, le=500)
    stop_loss_pct: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def needs_a_limit(self):
        if self.take_profit_pct is None and self.stop_loss_pct is None:
            raise ValueError("Set a take-profit or a stop-loss percentage.")
        return self

    @property
    def symbols(self) -> set[str]:
        return {self.symbol}

    @property
    def lookback(self) -> int:
        return 1

    def describe(self) -> str:
        parts = []
        if self.take_profit_pct:
            parts.append(f"up {self.take_profit_pct:g}%")
        if self.stop_loss_pct:
            parts.append(f"down {self.stop_loss_pct:g}%")
        return f"Sell all {self.symbol} once the position is {' or '.join(parts)}."

    def evaluate(self, bars: dict[str, list[BarLike]], day: date, held: int, average_price: float = 0) -> list[Signal]:
        series = bars.get(self.symbol) or []
        if held <= 0 or not average_price or not series or series[-1].date != day:
            return []
        change = (series[-1].close / average_price - 1) * 100
        if self.take_profit_pct and change >= self.take_profit_pct:
            return [Signal(self.symbol, "SELL", None, f"Take profit at {change:+.2f}%")]
        if self.stop_loss_pct and change <= -self.stop_loss_pct:
            return [Signal(self.symbol, "SELL", None, f"Stop loss at {change:+.2f}%")]
        return []


Rule = Annotated[PrevCloseMove | SmaCross | TakeProfitStopLoss, Field(discriminator="type")]
rule_adapter: TypeAdapter[Rule] = TypeAdapter(Rule)


def parse_rule(rule_type: str, params: dict) -> Rule:
    return rule_adapter.validate_python({**params, "type": rule_type})


def traded_symbol(rule: Rule) -> str:
    return rule.trade_symbol if isinstance(rule, PrevCloseMove) else rule.symbol


def evaluate(rule: Rule, bars: dict[str, list[BarLike]], day: date, positions: dict[str, tuple[int, float]]) -> list[Signal]:
    """`positions` maps symbol to (quantity, average_price)."""
    if isinstance(rule, TakeProfitStopLoss):
        held, average = positions.get(rule.symbol, (0, 0.0))
        return rule.evaluate(bars, day, held, average)
    symbol = rule.trade_symbol if isinstance(rule, PrevCloseMove) else rule.symbol
    return rule.evaluate(bars, day, positions.get(symbol, (0, 0.0))[0])
