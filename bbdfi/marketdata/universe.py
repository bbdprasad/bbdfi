"""Instruments the simulator tracks by default.

Edit NIFTY50 when the index is rebalanced. Symbols missing from a day's Bhavcopy are skipped.
Set UNIVERSE=all to store every NSE EQ series stock instead.
"""

INDICES = {
    "NIFTY 50": "Nifty 50 index",
    "NIFTY BANK": "Nifty Bank index",
}

NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV",
    "BAJFINANCE", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK",
    "INDUSINDBK", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]


def wants_symbol(symbol: str, universe: str) -> bool:
    return universe == "all" or symbol in NIFTY50
