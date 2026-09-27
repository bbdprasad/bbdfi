# Basis Paper

A small, Bootstrap-friendly paper-trading MVP. It includes an illustrative market dashboard, a watchlist, locally saved strategy switches, and a simulated buy/sell flow. **It does not connect to a broker or use live market data.**

## Run locally

From this directory, start any static file server, for example:

```sh
python3 -m http.server 4173
```

Then open <http://localhost:4173>.

The account is stored in this browser's local storage. To reset the demo account, clear site data for localhost.

## MVP boundaries

- Orders are simulated at fixed illustrative prices and never leave the browser.
- Account balance, positions, order history, and strategy toggles persist locally.
- The chart and leaderboard use illustrative/sample data.
- No sign-in, backend, payment flow, market-data feed, or broker integration is included.