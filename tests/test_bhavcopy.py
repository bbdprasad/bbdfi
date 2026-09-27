from bbdfi.marketdata.bhavcopy import parse_equity_csv, parse_index_csv

EQUITY = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4
2026-09-25,2026-09-25,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,,,,,RELIANCE INDUSTRIES LTD,1410.00,1432.50,1405.10,1428.30,1428.00,1410.80,,1428.30,,,8123456,11590000000,120000,F1,1,,,,,
2026-09-25,2026-09-25,CM,NSE,STK,1,INE000000000,RELIANCE,BL,,,,,RELIANCE INDUSTRIES LTD,1,1,1,1,1,1,,1,,,1,1,1,F1,1,,,,,
2026-09-25,2026-09-25,CM,NSE,STK,9999,INE999999999,TINYCO,EQ,,,,,TINY CO LTD,10,11,9,10.5,10.5,10,,10.5,,,100,1000,5,F1,1,,,,,
"""

INDEX = """Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield
Nifty 50,25-09-2026,25300.10,25450.00,25250.35,25418.75,171.60,0.68,312345678,32000.12,22.1,3.6,1.2
Nifty Bank,25-09-2026,57000.00,57250.00,56900.00,57182.40,239.45,0.42,-,-,15.0,2.4,0.9
Nifty IT,25-09-2026,1,1,1,1,0,0,-,-,-,-,-
"""


def test_parse_equity_filters_series_and_universe():
    bars = parse_equity_csv(EQUITY, "nifty50")
    assert [bar.symbol for bar in bars] == ["RELIANCE"]
    bar = bars[0]
    assert (bar.close, bar.prev_close, bar.volume, bar.date.isoformat()) == (1428.3, 1410.8, 8123456, "2026-09-25")
    assert {bar.symbol for bar in parse_equity_csv(EQUITY, "all")} == {"RELIANCE", "TINYCO"}


def test_parse_index():
    bars = {bar.symbol: bar for bar in parse_index_csv(INDEX)}
    assert set(bars) == {"NIFTY 50", "NIFTY BANK"}
    assert bars["NIFTY 50"].prev_close == 25247.15
    assert bars["NIFTY BANK"].volume == 0
