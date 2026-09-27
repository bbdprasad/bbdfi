# Road to a Bloomberg-style terminal

Bloomberg is four things at once: live data, deep analytics, a fast keyboard-driven workspace, and a
network (chat, news, research). BBDFi can get close on the workspace and analytics for Indian retail
traders cheaply. Live data and news cost money, so they are gated on revenue.

## Shipped

| Area | What exists |
| --- | --- |
| Workspace | `/terminal.html`: dark multi-panel terminal, command line with autocomplete and history, type-anywhere focus |
| Commands | `<SYMBOL>`, `<SYMBOL> GP/DES`, `BUY 10 INFY`, `SELL ALL INFY`, `MOV`, `HMAP`, `PORT`, `BLOT`, `RULES`, `RULE`, `LB`, `HELP` |
| Charts | Candlesticks with volume, SMA 20/50/200, EMA 20, Bollinger Bands, RSI and MACD panes, 1M to 2Y ranges |
| Security page | O/H/L/C, 52-week range, returns 1W to 1Y, 20-day and 1-year volatility, beta vs Nifty, RSI, distance from moving averages |
| Market monitor | Sortable watchlist, gainers, losers, most active by turnover, advance/decline and 52-week highs/lows |
| Heatmap | Nifty 50 by sector, tile size by turnover, colour by change |
| Portfolio | Equity, realized and unrealized P&L, win rate, Sharpe, volatility, max drawdown, beta, sector exposure |
| Strategies | Rule builder with a 90-day backtest, daily engine, 7-day leaderboard |

## Next, free data (no new cost)

1. **Wider universe.** Set `UNIVERSE=all` so every NSE EQ stock is in the monitor and heatmap. Add Nifty Next 50, Midcap 150 and sector indices from the same index file.
2. **Screener (`EQS`).** Filter by RSI, distance from moving averages, 52-week highs, volume spikes and sector, then save screens as watchlists.
3. **Custom watchlists and alerts (`ALRT`).** Price or indicator alerts checked in the daily job, shown in the terminal and emailed through Supabase.
4. **Comparison chart (`COMP`).** Rebase several symbols or a portfolio against Nifty on one chart.
5. **Correlation matrix (`CORR`).** Holdings vs each other and vs indices, to show concentration risk.
6. **F&O snapshot.** NSE publishes a free F&O Bhavcopy with open interest. Add option chains, put/call ratio and max pain, plus paper option trades (the original "buy a Call when Nifty drops" idea).
7. **Corporate actions.** Adjust history for splits and bonuses so charts and backtests stay correct.
8. **Richer backtests.** Brokerage and STT, slippage, walk-forward windows, and comparison to buy-and-hold.
9. **Keyboard layer.** F-key style shortcuts, several chart panels side by side, and saved layouts per user.

## Needs paid data (after subscriptions start)

- **Intraday and live ticks** from Kite Connect (about ₹2,000 a month) or Dhan/Fyers. This unlocks intraday rules, minute charts and a live tape over WebSockets.
- **Fundamentals** (P/E, earnings, shareholding) from a data vendor for a `FA` page.
- **News and filings.** Start with free NSE and BSE announcement feeds, then add a paid wire.

## Weeks 5 and 6 of the business plan

Razorpay subscription, then "Go Live" routing strategy orders to the user's own Kite or Angel One account.
The terminal's ticket and command line are the natural place for the Go Live switch.
