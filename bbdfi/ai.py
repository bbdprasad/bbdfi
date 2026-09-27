"""AI helpers: turn a plain-English idea into a rule, and explain a backtest.

Claude only drafts and explains. Every rule it drafts is validated by the same pydantic models
the engine uses, and every number it explains is computed here by the backtest, never by the model.
"""

import json
from datetime import date
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from bbdfi.config import get_settings
from bbdfi.engine.backtest import backtest
from bbdfi.engine.rules import PrevCloseMove, Rule, SmaCross, TakeProfitStopLoss, parse_rule
from bbdfi.models import AiUsage, Instrument

EDUCATION_NOTE = (
    "BBDFi is an educational paper-trading simulator for Indian markets. You help users express and "
    "understand their own trading ideas. Never recommend buying or selling a specific security, never "
    "predict prices, and never present results as investment advice. Past simulated results do not "
    "guarantee future returns."
)

RULE_TYPES = """Supported rule types (long-only, end-of-day, fills at the close):
1. prev_close_move: if watch_symbol closes threshold_pct% down/up vs yesterday's close, BUY or SELL
   quantity shares of trade_symbol. Fields: watch_symbol, direction (down|up), threshold_pct (0 to 20],
   trade_symbol, side (BUY|SELL), quantity (1 to 100000).
2. sma_cross: buy quantity shares of symbol when it closes above its period-day simple moving average,
   sell the whole position when it closes below. Fields: symbol, period (2 to 200), quantity.
3. take_profit_stop_loss: sell the whole position in symbol once it is up take_profit_pct% or down
   stop_loss_pct% from the average buy price. Fields: symbol, take_profit_pct (0 to 500],
   stop_loss_pct (0 to 100]. At least one of the two.
Anything else (options, futures, intraday, shorting, multiple conditions, other indicators) is not supported yet."""

_nullable = lambda kind: {"anyOf": [{"type": kind}, {"type": "null"}]}  # noqa: E731

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "reply": {"type": "string"},
        "name": {"type": "string"},
        "rule_type": {"type": "string", "enum": ["prev_close_move", "sma_cross", "take_profit_stop_loss", "none"]},
        "watch_symbol": _nullable("string"),
        "direction": {"anyOf": [{"type": "string", "enum": ["down", "up"]}, {"type": "null"}]},
        "threshold_pct": _nullable("number"),
        "trade_symbol": _nullable("string"),
        "side": {"anyOf": [{"type": "string", "enum": ["BUY", "SELL"]}, {"type": "null"}]},
        "symbol": _nullable("string"),
        "period": _nullable("integer"),
        "quantity": _nullable("integer"),
        "take_profit_pct": _nullable("number"),
        "stop_loss_pct": _nullable("number"),
    },
    "required": ["supported", "reply", "name", "rule_type", "watch_symbol", "direction", "threshold_pct",
                 "trade_symbol", "side", "symbol", "period", "quantity", "take_profit_pct", "stop_loss_pct"],
    "additionalProperties": False,
}

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
        "caution": {"type": "string"},
    },
    "required": ["headline", "points", "caution"],
    "additionalProperties": False,
}

FIELDS = {
    "prev_close_move": ["watch_symbol", "direction", "threshold_pct", "trade_symbol", "side", "quantity"],
    "sma_cross": ["symbol", "period", "quantity"],
    "take_profit_stop_loss": ["symbol", "take_profit_pct", "stop_loss_pct"],
}


class AiError(Exception):
    """A user-facing problem: the model refused, returned nothing usable, or the feature is off."""


class AiLimitReached(AiError):
    pass


@lru_cache
def get_client():
    import anthropic

    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _ask(system: str, prompt: str, schema: dict) -> dict:
    settings = get_settings()
    if not settings.ai_enabled:
        raise AiError("AI features are not configured on this server.")
    response = get_client().beta.messages.create(
        model=settings.ai_model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        cache_control={"type": "ephemeral"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise AiError("The assistant declined this request. Try describing a trading rule instead.")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise AiError("The assistant returned an unreadable answer. Please try again.") from error


def use_quota(session: Session, profile_id: str, today: date | None = None) -> int:
    """Count one AI call for today and return how many are left. Raises when the daily limit is used up."""
    limit = get_settings().ai_daily_limit
    today = today or date.today()
    usage = session.get(AiUsage, (profile_id, today))
    if usage is None:
        usage = AiUsage(profile_id=profile_id, day=today, count=0)
        session.add(usage)
    if usage.count >= limit:
        raise AiLimitReached(f"You have used all {limit} AI requests for today. They reset tomorrow.")
    usage.count += 1
    session.commit()
    return limit - usage.count


def _instrument_list(session: Session, limit: int = 400) -> str:
    rows = session.execute(select(Instrument.symbol, Instrument.name, Instrument.kind)
                           .order_by(Instrument.kind, Instrument.symbol).limit(limit)).all()
    return "\n".join(f"{symbol} ({kind}){': ' + name if name and name != symbol else ''}" for symbol, name, kind in rows)


def draft_rule(session: Session, text: str) -> dict:
    """Turn a plain-English (or Hindi, Tamil, Hinglish...) description into a validated rule."""
    system = (
        f"{EDUCATION_NOTE}\n\nYour job: convert the user's description of a trading rule into one of the "
        f"supported rule types below, filling only the fields that rule type uses and null for the rest.\n\n"
        f"{RULE_TYPES}\n\nUse only symbols from this list, exactly as written. Map company or index names "
        f"(for example 'Reliance' or 'Nifty') to the matching symbol.\n{_instrument_list(session)}\n\n"
        "If the user gives no quantity, use 10. If they give an amount in rupees instead of shares, set "
        "quantity to null and say so in the reply. If the idea cannot be expressed with a supported rule "
        "type, set supported to false and rule_type to none, and in the reply explain what is supported and "
        "suggest the closest rule the user could try instead. "
        "Write 'reply' in the same language and script the user wrote in: one or two short sentences that "
        "restate the rule in plain words and mention any assumption you made. 'name' is a short strategy "
        "name of at most 40 characters. Do not give advice about whether the idea is good."
    )
    answer = _ask(system, text, DRAFT_SCHEMA)
    result = {"reply": answer.get("reply", ""), "name": (answer.get("name") or "")[:80]}
    rule_type = answer.get("rule_type")
    if not answer.get("supported") or rule_type not in FIELDS:
        return result | {"supported": False}
    params = {field: answer[field] for field in FIELDS[rule_type] if answer.get(field) is not None}
    try:
        rule = parse_rule(rule_type, params)
    except ValidationError as error:
        return result | {"supported": False, "rule_type": rule_type, "params": params,
                         "problem": f"The drafted rule is incomplete: {error.errors()[0]['msg']}"}
    missing = sorted(symbol for symbol in rule.symbols if session.get(Instrument, symbol) is None)
    if missing:
        return result | {"supported": False, "rule_type": rule_type, "params": params,
                         "problem": f"Unknown instrument: {', '.join(missing)}"}
    return result | {"supported": True, "rule_type": rule_type, "params": params, "description": rule.describe()}


def variations(rule: Rule) -> list[tuple[str, Rule]]:
    """Nearby versions of the rule, to show whether the result depends on one lucky setting."""
    out: list[tuple[str, Rule]] = []
    if isinstance(rule, PrevCloseMove):
        for factor in (0.5, 1.5):
            threshold = round(min(20.0, rule.threshold_pct * factor), 2)
            if threshold != rule.threshold_pct:
                out.append((f"threshold {threshold:g}%", rule.model_copy(update={"threshold_pct": threshold})))
    elif isinstance(rule, SmaCross):
        for period in (10, 20, 50, 100):
            if period != rule.period:
                out.append((f"{period}-day average", rule.model_copy(update={"period": period})))
    elif isinstance(rule, TakeProfitStopLoss):
        for factor in (0.5, 1.5):
            update = {key: round(value * factor, 2) for key in ("take_profit_pct", "stop_loss_pct")
                      if (value := getattr(rule, key))}
            label = ", ".join(f"{'TP' if key == 'take_profit_pct' else 'SL'} {value:g}%" for key, value in update.items())
            out.append((label, rule.model_copy(update=update)))
    return out


def _summary(result: dict) -> dict:
    sells = [trade for trade in result.get("trades", []) if trade["side"] == "SELL"]
    return {"return_pct": result.get("return_pct"), "max_drawdown_pct": result.get("max_drawdown_pct"),
            "trades": len(result.get("trades", [])), "sells": len(sells), "rejected": result.get("rejected", 0)}


def explain_backtest(session: Session, rule: Rule, days: int, cash: float) -> dict:
    """Backtest the rule and a few variations, then have Claude explain the numbers in plain words."""
    main = backtest(session, rule, days, cash)
    if main.get("error"):
        raise AiError(main["error"])
    table = [{"variant": "your rule", **_summary(main)}]
    for label, variant in variations(rule):
        table.append({"variant": label, **_summary(backtest(session, variant, days, cash))})
    facts = {
        "rule": rule.describe(), "window": f"{main['start']} to {main['end']} ({main['days']} trading days)",
        "starting_cash": main["starting_cash"], "buy_and_hold": {"symbol": main["buy_and_hold_symbol"],
                                                                 "return_pct": main["buy_and_hold_pct"]},
        "results": table, "trades": main["trades"][:30],
    }
    system = (
        f"{EDUCATION_NOTE}\n\nYou are a backtest coach. Explain a simulated backtest to a retail trader who "
        "is learning. Use only the numbers given; do not invent any. Write simply, no jargon without a "
        "short explanation. Cover: how the rule did compared with simply buying and holding, what the "
        "drawdown means in rupees, and whether nearby variations tell the same story or the result looks "
        "like it depends on one lucky setting (overfitting). With fewer than 5 trades, say plainly that the "
        "sample is too small to conclude anything. Do not tell the user to trade or not trade the rule. "
        "'headline' is one sentence. 'points' has 2 to 4 short sentences. 'caution' is one sentence "
        "about the main limitation of this test."
    )
    answer = _ask(system, json.dumps(facts), EXPLAIN_SCHEMA)
    return {"headline": answer.get("headline", ""), "points": list(answer.get("points", []))[:6],
            "caution": answer.get("caution", ""), "variations": table,
            "buy_and_hold_pct": main["buy_and_hold_pct"], "buy_and_hold_symbol": main["buy_and_hold_symbol"]}
