"""Replay a rule over recent history with a fresh paper account."""

from bisect import bisect_right
from datetime import date

from sqlalchemy.orm import Session

from bbdfi.engine.fills import Rejected, fill
from bbdfi.engine.rules import Rule, evaluate
from bbdfi.marketdata.store import history, latest_date


def backtest(session: Session, rule: Rule, days: int = 90, cash: float = 1_000_000.0, until: date | None = None) -> dict:
    until = until or latest_date(session)
    if until is None:
        return {"error": "No market data loaded yet."}
    bars = history(session, rule.symbols, until, days + rule.lookback)
    all_days = sorted({bar.date for series in bars.values() for bar in series})
    test_days = all_days[-days:]
    dates = {symbol: [bar.date for bar in series] for symbol, series in bars.items()}

    starting_cash = cash
    positions: dict[str, tuple[int, float]] = {}
    trades, curve = [], []
    rejected = 0
    for day in test_days:
        view = {symbol: series[: bisect_right(dates[symbol], day)] for symbol, series in bars.items()}
        for signal in evaluate(rule, view, day, positions):
            series = view.get(signal.symbol) or []
            if not series or series[-1].date != day:
                continue
            price = series[-1].close
            held, average = positions.get(signal.symbol, (0, 0.0))
            try:
                result = fill(cash, held, average, signal.side, signal.quantity, price)
            except Rejected:
                rejected += 1
                continue
            cash = result.cash
            positions[signal.symbol] = (result.held, result.average_price)
            trades.append({"date": day.isoformat(), "symbol": signal.symbol, "side": signal.side,
                           "quantity": result.quantity, "price": price, "reason": signal.reason})
        equity = cash
        for symbol, (held, average) in positions.items():
            series = view.get(symbol) or []
            equity += held * (series[-1].close if series else average)
        curve.append({"date": day.isoformat(), "equity": round(equity, 2)})

    peak, max_drawdown = starting_cash, 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        max_drawdown = max(max_drawdown, (peak - point["equity"]) / peak * 100)
    final = curve[-1]["equity"] if curve else starting_cash
    return {
        "start": test_days[0].isoformat() if test_days else None,
        "end": test_days[-1].isoformat() if test_days else None,
        "days": len(test_days),
        "starting_cash": starting_cash,
        "final_equity": final,
        "return_pct": round((final / starting_cash - 1) * 100, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "trades": trades,
        "rejected": rejected,
        "equity_curve": curve,
    }
