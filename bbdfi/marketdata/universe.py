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


SECTORS = {
    "Financials": ["AXISBANK", "BAJAJFINSV", "BAJFINANCE", "HDFCBANK", "HDFCLIFE", "ICICIBANK", "INDUSINDBK",
                   "JIOFIN", "KOTAKBANK", "SBILIFE", "SBIN", "SHRIRAMFIN"],
    "IT": ["HCLTECH", "INFY", "TCS", "TECHM", "WIPRO"],
    "Energy & Power": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA"],
    "Auto": ["BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "M&M", "MARUTI"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "TATACONSUM"],
    "Healthcare": ["APOLLOHOSP", "CIPLA", "DRREDDY", "SUNPHARMA"],
    "Metals & Mining": ["ADANIENT", "HINDALCO", "JSWSTEEL", "TATASTEEL"],
    "Industrials": ["ADANIPORTS", "BEL", "GRASIM", "LT", "ULTRACEMCO"],
    "Consumer": ["ASIANPAINT", "ETERNAL", "TITAN", "TRENT"],
    "Telecom": ["BHARTIARTL"],
}
SECTOR_OF = {symbol: sector for sector, symbols in SECTORS.items() for symbol in symbols}


def sector_of(symbol: str) -> str:
    if symbol in INDICES:
        return "Index"
    return SECTOR_OF.get(symbol, "Other")
