# BBDFi

A paper-trading strategy simulator for Indian retail traders. Users build simple rules ("if Nifty 50
drops 1.5% below yesterday's close, buy HDFCBANK"), preview them on the last 90 market days, switch
them on, and compete on a public 7-day leaderboard. No real money moves and nothing is sent to a broker.

Stack: Python (FastAPI + SQLAlchemy) on Supabase Postgres and Supabase Auth, with a Bootstrap front end
served by the same app. Prices are free NSE end-of-day Bhavcopy files.

## Run locally

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn bbdfi.main:app --reload
```

Open <http://localhost:8000>. With no settings, the app uses a local SQLite file, loads clearly labelled
sample prices, and lets you sign in with just a handle. Open a second browser with another handle to see
the leaderboard move.

Load real NSE prices instead (run from a machine in India if NSE blocks your network):

```sh
python -m bbdfi.cli backfill --days 180   # last ~6 months of closes
python -m bbdfi.cli run-engine            # run active strategies and snapshot equity
```

Run the tests with `pytest -q`.

## Connect Supabase

1. Create a Supabase project (the free tier is enough to start; pick the Mumbai region).
2. Copy `.env.example` to `.env` and fill in `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_ANON_KEY`.
3. In Supabase, Authentication > URL Configuration, add your site URL (e.g. `http://localhost:8000`) so
   the email sign-in link returns to the app.
4. `python -m bbdfi.cli init-db` creates the tables and enables row level security on each one. The API
   connects as the database owner, so RLS with no policies simply blocks direct access with the public
   anon key.
5. `python -m bbdfi.cli backfill --days 180` loads history.

## Daily job

After NSE publishes the Bhavcopy (around 6 PM IST), run:

```sh
python -m bbdfi.cli daily
```

It loads the day's closes, runs every active strategy at the closing price, and snapshots each account's
equity for the leaderboard. It is safe to run more than once. Two ways to schedule it:

- GitHub Actions: `.github/workflows/daily.yml` runs at 7:30 PM IST on weekdays. Add a `DATABASE_URL`
  repository secret and set the repository variable `DAILY_JOB_ENABLED=true`.
- Any cron service: set `ADMIN_TOKEN` on the server and call
  `POST /api/admin/run-daily` with the header `X-Admin-Token`.

NSE sometimes blocks requests from cloud IP ranges. If the job loads 0 bars on a trading day, run it from
a machine in India or switch to a paid data source.

## How it fits together

| Path | What it does |
| --- | --- |
| `bbdfi/marketdata/` | Downloads and parses NSE equity and index closes, plus the sample data generator |
| `bbdfi/engine/rules.py` | The three rule types and how each turns prices into order signals |
| `bbdfi/engine/broker.py` | Paper broker: long-only fills at the closing price against cash and positions |
| `bbdfi/engine/runner.py` | Daily run: evaluates active strategies once per market day and snapshots equity |
| `bbdfi/engine/backtest.py` | Replays a rule over recent history for the "Preview" button |
| `bbdfi/leaderboard.py` | 7-day return ranking |
| `bbdfi/api/routes.py` | JSON API used by the front end |
| `web/` | Dashboard and public leaderboard page |

## Rules and limits

- Paper orders fill at the latest NSE closing price. There is no intraday data yet, so rules run once per
  day after the close.
- Long only: sells are capped at what you hold. Brokerage and taxes are not modelled.
- A new or re-enabled strategy starts from the next market close, so it never trades on prices that
  were already known when it was switched on.
- Every account starts with ₹10,00,000 of paper cash.

## Not built yet

Razorpay subscription, the "Go Live" button, and routing orders to a user's own Zerodha Kite or Angel One
account (weeks 5 and 6 of the plan).
