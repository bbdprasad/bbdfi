"""Download and parse NSE end-of-day files (free, published around 6 PM IST on trading days).

Equities use the UDiFF Bhavcopy format NSE switched to in July 2024. Indices come from the
daily "ind_close_all" file.
"""

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from bbdfi.marketdata.universe import INDICES, wants_symbol

EQUITY_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
INDEX_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{dmy}.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}


@dataclass
class Bar:
    symbol: str
    name: str
    kind: str
    date: date
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: float


class NoDataForDate(Exception):
    """NSE published nothing for this date (weekend, holiday, or not out yet)."""


def _num(value: str | None) -> float | None:
    value = (value or "").strip().replace(",", "")
    if value in ("", "-"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_equity_csv(text: str, universe: str = "nifty50") -> list[Bar]:
    bars = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {key.strip(): value for key, value in row.items() if key}
        if row.get("SctySrs", "").strip() != "EQ":
            continue
        symbol = row["TckrSymb"].strip()
        if not wants_symbol(symbol, universe):
            continue
        close = _num(row.get("ClsPric"))
        if close is None:
            continue
        bars.append(Bar(
            symbol=symbol,
            name=(row.get("FinInstrmNm") or symbol).strip(),
            kind="EQ",
            date=date.fromisoformat(row["TradDt"].strip()),
            open=_num(row.get("OpnPric")) or close,
            high=_num(row.get("HghPric")) or close,
            low=_num(row.get("LwPric")) or close,
            close=close,
            prev_close=_num(row.get("PrvsClsgPric")) or close,
            volume=_num(row.get("TtlTradgVol")) or 0,
        ))
    return bars


def parse_index_csv(text: str) -> list[Bar]:
    bars = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {key.strip(): (value or "").strip() for key, value in row.items() if key}
        name = row.get("Index Name", "")
        symbol = name.upper()
        if symbol not in INDICES:
            continue
        close = _num(row.get("Closing Index Value"))
        if close is None:
            continue
        change = _num(row.get("Points Change")) or 0
        bars.append(Bar(
            symbol=symbol,
            name=INDICES[symbol],
            kind="INDEX",
            date=datetime.strptime(row["Index Date"], "%d-%m-%Y").date(),
            open=_num(row.get("Open Index Value")) or close,
            high=_num(row.get("High Index Value")) or close,
            low=_num(row.get("Low Index Value")) or close,
            close=close,
            prev_close=round(close - change, 2),
            volume=_num(row.get("Volume")) or 0,
        ))
    return bars


def _get(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    if response.status_code == 404:
        raise NoDataForDate(url)
    response.raise_for_status()
    return response.content


def fetch_day(day: date, universe: str = "nifty50", client: httpx.Client | None = None) -> list[Bar]:
    owns_client = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)
    try:
        raw = _get(client, EQUITY_URL.format(ymd=day.strftime("%Y%m%d")))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            equity_text = archive.read(archive.namelist()[0]).decode("utf-8-sig")
        bars = parse_equity_csv(equity_text, universe)
        try:
            index_text = _get(client, INDEX_URL.format(dmy=day.strftime("%d%m%Y"))).decode("utf-8-sig")
            bars += parse_index_csv(index_text)
        except NoDataForDate:
            pass
        return bars
    finally:
        if owns_client:
            client.close()
