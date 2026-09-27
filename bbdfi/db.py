from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bbdfi.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # Supabase's transaction pooler (port 6543) does not support prepared statements.
    return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def init_db(bind: Engine | None = None) -> None:
    """Create tables. On Postgres (Supabase) also enable row level security.

    The API connects with the database owner role, which bypasses RLS. Enabling RLS with no
    policies stops anyone holding the public anon key from reading or writing these tables
    through Supabase's auto-generated REST API.
    """
    from bbdfi import models  # noqa: F401  registers tables

    bind = bind or engine
    Base.metadata.create_all(bind)
    if bind.dialect.name == "postgresql":
        with bind.begin() as connection:
            for table in Base.metadata.sorted_tables:
                connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
