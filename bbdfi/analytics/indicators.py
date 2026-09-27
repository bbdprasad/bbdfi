"""Technical indicators over a list of closes. Each returns a list aligned to the input,
with None where there is not enough history yet."""

import math


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = values[i] * k + current * (1 - k)
        out[i] = current
    return out


def bollinger(values: list[float], period: int = 20, width: float = 2.0) -> tuple[list, list]:
    middle = sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1: i + 1]
        mean = middle[i]
        deviation = math.sqrt(sum((v - mean) ** 2 for v in window) / period)
        upper[i], lower[i] = mean + width * deviation, mean - width * deviation
    return upper, lower


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0)
        losses += max(-change, 0)
    avg_gain, avg_loss = gains / period, losses / period

    def value() -> float:
        return 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)

    out[period] = value()
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0)) / period
        out[i] = value()
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list, list, list]:
    fast_ema, slow_ema = ema(values, fast), ema(values, slow)
    line = [f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    signal_part = ema([v for v in line[start:]], signal) if start < len(line) else []
    signal_line = [None] * start + signal_part
    histogram = [l - s if l is not None and s is not None else None for l, s in zip(line, signal_line)]
    return line, signal_line, histogram


def daily_returns(values: list[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1]]


def annualized_volatility(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252) * 100


def beta(asset: list[float], market: list[float]) -> float | None:
    n = min(len(asset), len(market))
    if n < 10:
        return None
    asset, market = asset[-n:], market[-n:]
    mean_a, mean_m = sum(asset) / n, sum(market) / n
    covariance = sum((a - mean_a) * (m - mean_m) for a, m in zip(asset, market))
    variance = sum((m - mean_m) ** 2 for m in market)
    return covariance / variance if variance else None


def max_drawdown(values: list[float]) -> float:
    peak, worst = values[0] if values else 0, 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = max(worst, (peak - value) / peak * 100)
    return worst
