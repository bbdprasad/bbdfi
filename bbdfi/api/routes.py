from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bbdfi import ai
from bbdfi.analytics import market as market_analytics
from bbdfi.analytics.portfolio import analytics as portfolio_analytics
from bbdfi.api.schemas import AiExplainIn, AiStrategyIn, BacktestIn, CommandIn, OrderIn, ProfilePatch, StrategyIn, StrategyPatch
from bbdfi.auth import current_profile
from bbdfi.commands import parse as parse_command
from bbdfi.config import Settings, get_settings
from bbdfi.db import get_session
from bbdfi.engine.backtest import backtest
from bbdfi.engine.broker import place_order
from bbdfi.engine.fills import Rejected
from bbdfi.engine.rules import Rule, parse_rule
from bbdfi.engine.runner import run_pending
from bbdfi.jobs import ingest_day
from bbdfi.leaderboard import leaderboard
from bbdfi.marketdata.store import closes_on, latest_date
from bbdfi.models import DailyBar, EquitySnapshot, Instrument, Order, Position, Profile, Strategy

router = APIRouter(prefix="/api")


def _rule_or_422(rule_type: str, params: dict) -> Rule:
    try:
        return parse_rule(rule_type, params)
    except ValidationError as error:
        messages = "; ".join(f"{'.'.join(map(str, e['loc'][1:])) or 'rule'}: {e['msg']}" for e in error.errors())
        raise HTTPException(422, messages) from error


def _check_symbols(session: Session, rule: Rule) -> None:
    missing = [symbol for symbol in rule.symbols if session.get(Instrument, symbol) is None]
    if missing:
        raise HTTPException(422, f"Unknown instrument: {', '.join(sorted(missing))}")


def _strategy_out(strategy: Strategy) -> dict:
    try:
        description = parse_rule(strategy.rule_type, strategy.params).describe()
    except ValidationError:
        description = "Invalid rule"
    return {
        "id": strategy.id, "name": strategy.name, "rule_type": strategy.rule_type, "params": strategy.params,
        "active": strategy.active, "description": description,
        "last_run_date": strategy.last_run_date.isoformat() if strategy.last_run_date else None,
        "start_after": strategy.start_after.isoformat() if strategy.start_after else None,
    }


def _order_out(order: Order, names: dict[str, str]) -> dict:
    return {
        "id": order.id, "symbol": order.symbol, "side": order.side, "quantity": order.quantity,
        "price": order.price, "status": order.status, "source": order.source, "note": order.note,
        "strategy": names.get(order.strategy_id) if order.strategy_id else None,
        "trade_date": order.trade_date.isoformat(), "created_at": order.created_at.isoformat(),
    }


# ---- public -------------------------------------------------------------

@router.get("/config")
def config(settings: Settings = Depends(get_settings)):
    return {"auth_mode": settings.resolved_auth_mode, "supabase_url": settings.supabase_url,
            "supabase_anon_key": settings.supabase_anon_key, "ai_enabled": settings.ai_enabled}


@router.get("/market/status")
def market_status(session: Session = Depends(get_session)):
    day = latest_date(session)
    sources = set(session.scalars(select(DailyBar.source).where(DailyBar.date == day).distinct())) if day else set()
    return {"as_of": day.isoformat() if day else None, "sample_data": "sample" in sources,
            "instruments": session.scalar(select(func.count()).select_from(Instrument))}


@router.get("/market/quotes")
def quotes(session: Session = Depends(get_session)):
    day = latest_date(session)
    if day is None:
        return []
    latest = (select(DailyBar.symbol, func.max(DailyBar.date).label("d")).group_by(DailyBar.symbol).subquery())
    rows = session.execute(
        select(Instrument, DailyBar)
        .join(latest, Instrument.symbol == latest.c.symbol)
        .join(DailyBar, (DailyBar.symbol == latest.c.symbol) & (DailyBar.date == latest.c.d))
    ).all()
    result = [{
        "symbol": instrument.symbol, "name": instrument.name, "kind": instrument.kind,
        "close": bar.close, "prev_close": bar.prev_close, "date": bar.date.isoformat(),
        "change_pct": round((bar.close / bar.prev_close - 1) * 100, 2) if bar.prev_close else 0,
    } for instrument, bar in rows]
    result.sort(key=lambda quote: (quote["kind"] != "INDEX", quote["symbol"]))
    return result


@router.get("/market/history")
def price_history(symbol: str, days: int = Query(default=90, ge=5, le=750), session: Session = Depends(get_session)):
    bars = list(session.scalars(
        select(DailyBar).where(DailyBar.symbol == symbol).order_by(DailyBar.date.desc()).limit(days)))
    if not bars:
        raise HTTPException(404, "No data for that instrument")
    return [{"date": bar.date.isoformat(), "open": bar.open, "high": bar.high, "low": bar.low,
             "close": bar.close} for bar in reversed(bars)]


@router.get("/market/movers")
def market_movers(session: Session = Depends(get_session)):
    return market_analytics.movers(session)


@router.get("/market/heatmap")
def market_heatmap(session: Session = Depends(get_session)):
    return market_analytics.heatmap(session)


@router.get("/market/describe")
def market_describe(symbol: str, session: Session = Depends(get_session)):
    result = market_analytics.describe(session, symbol)
    if result is None:
        raise HTTPException(404, "No data for that instrument")
    return result


@router.get("/market/chart")
def market_chart(symbol: str, days: int = Query(default=126, ge=5, le=750), indicators: str = "",
                 session: Session = Depends(get_session)):
    wanted = {name.strip().lower() for name in indicators.split(",") if name.strip()}
    result = market_analytics.chart(session, symbol, days, wanted)
    if result is None:
        raise HTTPException(404, "No data for that instrument")
    return result


@router.post("/command")
def command(body: CommandIn, session: Session = Depends(get_session)):
    return parse_command(body.text, set(session.scalars(select(Instrument.symbol))))


@router.get("/leaderboard")
def get_leaderboard(session: Session = Depends(get_session)):
    return leaderboard(session)


# ---- signed in ----------------------------------------------------------

@router.get("/me")
def me(profile: Profile = Depends(current_profile)):
    return {"handle": profile.handle, "display_name": profile.display_name}


@router.patch("/me")
def update_me(body: ProfilePatch, profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    if body.handle and body.handle != profile.handle:
        if session.scalar(select(Profile.id).where(Profile.handle == body.handle)):
            raise HTTPException(409, "That handle is taken")
        profile.handle = body.handle
    if body.display_name:
        profile.display_name = body.display_name
    session.commit()
    return {"handle": profile.handle, "display_name": profile.display_name}


@router.get("/account")
def account(profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    day = latest_date(session)
    closes = closes_on(session, day) if day else {}
    positions = []
    for position in session.scalars(select(Position).where(Position.profile_id == profile.id).order_by(Position.symbol)):
        price = closes.get(position.symbol, position.average_price)
        positions.append({
            "symbol": position.symbol, "quantity": position.quantity, "average_price": position.average_price,
            "last_price": price, "market_value": round(position.quantity * price, 2),
            "pnl": round(position.quantity * (price - position.average_price), 2),
            "pnl_pct": round((price / position.average_price - 1) * 100, 2) if position.average_price else 0,
        })
    market_value = sum(p["market_value"] for p in positions)
    invested = sum(p["quantity"] * p["average_price"] for p in positions)
    unrealized = sum(p["pnl"] for p in positions)
    equity = profile.cash + market_value
    curve = [{"date": s.date.isoformat(), "equity": s.equity} for s in session.scalars(
        select(EquitySnapshot).where(EquitySnapshot.profile_id == profile.id).order_by(EquitySnapshot.date))]
    order_count = session.scalar(select(func.count()).select_from(Order).where(
        Order.profile_id == profile.id, Order.status == "filled"))
    return {
        "handle": profile.handle, "display_name": profile.display_name,
        "cash": round(profile.cash, 2), "equity": round(equity, 2), "starting_cash": profile.starting_cash,
        "total_return_pct": round((equity / profile.starting_cash - 1) * 100, 2),
        "unrealized_pnl": round(unrealized, 2),
        "unrealized_pct": round(unrealized / invested * 100, 2) if invested else 0,
        "positions": positions, "orders_filled": order_count, "equity_curve": curve,
        "prices_as_of": day.isoformat() if day else None,
    }


@router.get("/account/analytics")
def account_analytics(profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    return portfolio_analytics(session, profile)


@router.get("/orders")
def orders(limit: int = Query(default=50, ge=1, le=500), profile: Profile = Depends(current_profile),
           session: Session = Depends(get_session)):
    names = dict(session.execute(select(Strategy.id, Strategy.name).where(Strategy.profile_id == profile.id)).all())
    rows = session.scalars(select(Order).where(Order.profile_id == profile.id)
                           .order_by(Order.created_at.desc()).limit(limit))
    return [_order_out(order, names) for order in rows]


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    bar = session.scalars(select(DailyBar).where(DailyBar.symbol == body.symbol)
                          .order_by(DailyBar.date.desc()).limit(1)).first()
    if bar is None:
        raise HTTPException(404, "No price for that instrument")
    if body.side == "BUY" and body.quantity is None:
        raise HTTPException(422, "Enter a quantity to buy")
    try:
        order = place_order(session, profile, body.symbol, body.side, body.quantity, bar.close, bar.date,
                            note=f"Filled at {bar.date:%d %b} close")
    except Rejected as error:
        raise HTTPException(422, str(error)) from error
    session.commit()
    return _order_out(order, {})


@router.get("/strategies")
def strategies(profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    rows = session.scalars(select(Strategy).where(Strategy.profile_id == profile.id).order_by(Strategy.created_at))
    return [_strategy_out(strategy) for strategy in rows]


@router.post("/strategies", status_code=201)
def create_strategy(body: StrategyIn, profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    rule = _rule_or_422(body.rule_type, body.params)
    _check_symbols(session, rule)
    count = session.scalar(select(func.count()).select_from(Strategy).where(Strategy.profile_id == profile.id))
    if count >= 20:
        raise HTTPException(422, "You can keep up to 20 strategies")
    strategy = Strategy(profile_id=profile.id, name=body.name, rule_type=rule.type,
                        params=rule.model_dump(exclude={"type"}), active=body.active,
                        start_after=latest_date(session))
    session.add(strategy)
    session.commit()
    return _strategy_out(strategy)


def _own_strategy(strategy_id: str, profile: Profile, session: Session) -> Strategy:
    strategy = session.get(Strategy, strategy_id)
    if strategy is None or strategy.profile_id != profile.id:
        raise HTTPException(404, "Strategy not found")
    return strategy


@router.patch("/strategies/{strategy_id}")
def update_strategy(strategy_id: str, body: StrategyPatch, profile: Profile = Depends(current_profile),
                    session: Session = Depends(get_session)):
    strategy = _own_strategy(strategy_id, profile, session)
    if body.name is not None:
        strategy.name = body.name
    if body.active is not None and body.active != strategy.active:
        strategy.active = body.active
        if body.active:
            # A paused rule resumes from the next market day, not retroactively.
            strategy.start_after = max(filter(None, [strategy.start_after, latest_date(session)]), default=None)
    session.commit()
    return _strategy_out(strategy)


@router.delete("/strategies/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: str, profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    session.delete(_own_strategy(strategy_id, profile, session))
    session.commit()


@router.post("/strategies/backtest")
def run_backtest(body: BacktestIn, profile: Profile = Depends(current_profile), session: Session = Depends(get_session)):
    rule = _rule_or_422(body.rule_type, body.params)
    _check_symbols(session, rule)
    return {"description": rule.describe(), **backtest(session, rule, body.days, profile.starting_cash)}


# ---- AI -----------------------------------------------------------------

def _ai_quota(session: Session, profile: Profile, settings: Settings) -> int:
    if not settings.ai_enabled:
        raise HTTPException(503, "AI features are not configured on this server.")
    try:
        return ai.use_quota(session, profile.id)
    except ai.AiLimitReached as error:
        raise HTTPException(429, str(error)) from error


@router.post("/ai/strategy")
def ai_strategy(body: AiStrategyIn, profile: Profile = Depends(current_profile), session: Session = Depends(get_session),
                settings: Settings = Depends(get_settings)):
    remaining = _ai_quota(session, profile, settings)
    try:
        return {**ai.draft_rule(session, body.text), "remaining_today": remaining}
    except ai.AiError as error:
        raise HTTPException(502, str(error)) from error


@router.post("/ai/explain")
def ai_explain(body: AiExplainIn, profile: Profile = Depends(current_profile), session: Session = Depends(get_session),
               settings: Settings = Depends(get_settings)):
    rule = _rule_or_422(body.rule_type, body.params)
    _check_symbols(session, rule)
    remaining = _ai_quota(session, profile, settings)
    try:
        return {**ai.explain_backtest(session, rule, body.days, profile.starting_cash), "remaining_today": remaining}
    except ai.AiError as error:
        raise HTTPException(502, str(error)) from error


# ---- admin --------------------------------------------------------------

@router.post("/admin/run-daily")
def admin_run_daily(day: date | None = None, x_admin_token: str | None = Header(default=None),
                    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(403, "Forbidden")
    loaded = ingest_day(session, day or date.today(), settings.universe)
    summaries = run_pending(session)
    return {"bars_loaded": loaded, "days_run": [s.__dict__ | {"day": s.day.isoformat()} for s in summaries]}
