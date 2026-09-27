"""Terminal command line, Bloomberg style: "RELIANCE <GO>", "BUY 10 INFY", "MOV", "HELP"."""

import re

ALIASES = {"NIFTY": "NIFTY 50", "NIFTY50": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "NIFTYBANK": "NIFTY BANK"}
FUNCTIONS = {
    "HELP": "help", "?": "help",
    "MOV": "movers", "MOST": "movers", "MOVERS": "movers",
    "HMAP": "heatmap", "HEAT": "heatmap", "IMAP": "heatmap",
    "PORT": "portfolio", "PF": "portfolio", "RISK": "portfolio",
    "LB": "leaderboard", "LEAD": "leaderboard", "RANK": "leaderboard",
    "RULES": "strategies", "STRAT": "strategies", "RULE": "new_rule", "NEW": "new_rule",
    "BLOT": "orders", "ORD": "orders", "ORDERS": "orders",
}
SECURITY_VIEWS = {"DES": "des", "GP": "chart", "CHART": "chart", "TRADE": "trade"}
HELP = [
    ("<SYMBOL>", "Chart and description, e.g. RELIANCE or NIFTY"),
    ("BUY 10 INFY", "Paper buy at the last close (B for short)"),
    ("SELL ALL INFY", "Paper sell a quantity or your whole position (S for short)"),
    ("MOV", "Top gainers, losers, most active and market breadth"),
    ("HMAP", "Sector heatmap"),
    ("PORT", "Portfolio risk: Sharpe, drawdown, beta, sector exposure"),
    ("RULES / RULE", "Your strategies / build a new one"),
    ("RULE <idea>", "Draft a rule from plain words with AI"),
    ("BLOT", "Order blotter"),
    ("LB", "Weekly leaderboard"),
]


def _resolve(token: str, symbols: set[str]) -> str | None:
    token = token.upper().strip()
    if token in symbols:
        return token
    alias = ALIASES.get(token.replace(" ", ""))
    return alias if alias in symbols else None


def _suggest(token: str, symbols: set[str]) -> list[str]:
    token = token.upper()
    starts = sorted(s for s in symbols if s.startswith(token))
    contains = sorted(s for s in symbols if token in s and s not in starts)
    return (starts + contains)[:5]


def parse(text: str, symbols: set[str]) -> dict:
    text = re.sub(r"\s*<?\bGO\b>?\s*$", "", text.strip(), flags=re.IGNORECASE).strip()
    if not text:
        return {"action": "error", "message": "Type a symbol or a function. HELP lists them."}
    upper = text.upper()
    if upper in FUNCTIONS:
        result = {"action": FUNCTIONS[upper]}
        if result["action"] == "help":
            result["commands"] = [{"command": c, "does": d} for c, d in HELP]
        return result

    # RULE <idea> or AI <idea> opens the builder with the idea drafted by AI.
    idea = re.fullmatch(r"(?:RULE|AI)\s+(.+)", text, flags=re.IGNORECASE)
    if idea:
        return {"action": "new_rule", "text": idea.group(1).strip()}

    trade = re.fullmatch(r"(BUY|B|SELL|S)\s+(\d+|ALL)\s+(.+)", upper)
    if trade:
        side = "BUY" if trade.group(1) in ("BUY", "B") else "SELL"
        symbol = _resolve(trade.group(3), symbols)
        if symbol is None:
            return {"action": "error", "message": f"Unknown instrument {trade.group(3)}",
                    "suggestions": _suggest(trade.group(3), symbols)}
        if trade.group(2) == "ALL":
            if side == "BUY":
                return {"action": "error", "message": "BUY needs a quantity, e.g. BUY 10 INFY"}
            return {"action": "order", "side": side, "quantity": None, "symbol": symbol}
        quantity = int(trade.group(2))
        if quantity < 1:
            return {"action": "error", "message": "Quantity must be at least 1"}
        return {"action": "order", "side": side, "quantity": quantity, "symbol": symbol}

    parts = upper.rsplit(" ", 1)
    view = "des"
    if len(parts) == 2 and parts[1] in SECURITY_VIEWS:
        upper, view = parts[0], SECURITY_VIEWS[parts[1]]
    symbol = _resolve(upper, symbols)
    if symbol:
        return {"action": "security", "symbol": symbol, "view": view}
    suggestions = _suggest(upper, symbols)
    return {"action": "error", "message": f"No instrument or function called {text}", "suggestions": suggestions}
