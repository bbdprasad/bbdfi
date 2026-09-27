import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["AUTH_MODE"] = "dev"
os.environ["ADMIN_TOKEN"] = "secret"
os.environ["SEED_SAMPLE_ON_EMPTY"] = "false"

from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from bbdfi.db import Base, SessionLocal, engine, init_db  # noqa: E402
from bbdfi.marketdata.bhavcopy import Bar  # noqa: E402
from bbdfi.marketdata.store import save_bars  # noqa: E402


@pytest.fixture()
def session():
    Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as db:
        yield db


def make_bars(symbol: str, closes: list[float], start: date = date(2026, 9, 1), kind: str = "EQ") -> list[Bar]:
    bars, prev, day = [], closes[0], start
    for close in closes:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        bars.append(Bar(symbol, symbol, kind, day, prev, max(prev, close), min(prev, close), close, prev, 1000))
        prev = close
        day += timedelta(days=1)
    return bars


@pytest.fixture()
def load(session):
    def _load(symbol, closes, kind="EQ"):
        bars = make_bars(symbol, closes, kind=kind)
        save_bars(session, bars)
        session.commit()
        return bars
    return _load


@pytest.fixture()
def client(session):
    from bbdfi.main import app
    with TestClient(app) as test_client:
        yield test_client


def auth(handle: str) -> dict:
    return {"Authorization": f"Bearer dev:{handle}"}
