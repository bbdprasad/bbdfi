from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase Postgres connection string, e.g.
    # postgresql+psycopg://postgres.<ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
    # Falls back to a local SQLite file for development.
    database_url: str = "sqlite:///./bbdfi.db"

    # Supabase project settings. When supabase_url is set, the API requires a Supabase login.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # Legacy HS256 secret. Leave empty to verify tokens with the project's JWKS (asymmetric keys).
    supabase_jwt_secret: str = ""

    # "dev" lets anyone sign in with just a handle (local development only).
    # "supabase" verifies Supabase Auth access tokens. Empty means: supabase if supabase_url is set, else dev.
    auth_mode: str = ""

    # Protects POST /api/admin/run-daily, for external cron services.
    admin_token: str = ""

    # In dev mode, load labelled sample prices on startup when the database has no prices yet.
    seed_sample_on_empty: bool = True

    starting_cash: float = 1_000_000.0
    # "nifty50" keeps the database small; "all" stores every NSE EQ series stock.
    universe: str = "nifty50"

    @property
    def resolved_auth_mode(self) -> str:
        if self.auth_mode:
            return self.auth_mode
        return "supabase" if self.supabase_url else "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
