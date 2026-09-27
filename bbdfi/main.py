from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bbdfi.api.routes import router
from bbdfi.config import get_settings
from bbdfi.db import SessionLocal, init_db
from bbdfi.engine.runner import run_pending
from bbdfi.jobs import seed_sample
from bbdfi.marketdata.store import latest_date

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    if settings.resolved_auth_mode == "dev" and settings.seed_sample_on_empty:
        # Local development: make the app usable immediately with labelled sample prices.
        with SessionLocal() as session:
            if latest_date(session) is None:
                seed_sample(session)
                run_pending(session)
    yield


app = FastAPI(title="BBDFi", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
