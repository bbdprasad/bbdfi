"""Resolve the signed-in user from the Authorization header.

supabase mode: verifies a Supabase Auth access token (JWKS for asymmetric keys, or the legacy
HS256 secret when SUPABASE_JWT_SECRET is set).
dev mode: accepts "Bearer dev:<handle>" so the app can run locally without Supabase.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bbdfi.config import Settings, get_settings
from bbdfi.db import get_session
from bbdfi.models import Profile


@dataclass
class Identity:
    user_id: str
    email: str
    name: str


HANDLE_PATTERN = re.compile(r"^[a-z0-9_]{3,20}$")


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def verify_supabase_token(token: str, settings: Settings) -> Identity:
    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        else:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["ES256", "RS256"], audience="authenticated")
    except jwt.PyJWTError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid session: {error}") from error
    email = claims.get("email") or ""
    metadata = claims.get("user_metadata") or {}
    return Identity(claims["sub"], email, metadata.get("full_name") or metadata.get("name") or email.split("@")[0])


def identity_from_header(authorization: str | None, settings: Settings) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    token = authorization[7:].strip()
    if settings.resolved_auth_mode == "dev":
        if not token.startswith("dev:"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dev mode expects a dev:<handle> token")
        handle = token[4:].lower()
        if not HANDLE_PATTERN.match(handle):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Handle must be 3 to 20 letters, digits or _")
        return Identity(f"dev:{handle}", "", handle)
    return verify_supabase_token(token, settings)


def _unique_handle(session: Session, wanted: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", wanted.lower())[:16] or "trader"
    if len(base) < 3:
        base = f"{base}_trader"[:16]
    handle, suffix = base, 1
    while session.scalar(select(Profile.id).where(Profile.handle == handle)):
        suffix += 1
        handle = f"{base}{suffix}"
    return handle


def current_profile(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Profile:
    identity = identity_from_header(authorization, settings)
    profile = session.get(Profile, identity.user_id)
    if profile is None:
        profile = Profile(
            id=identity.user_id,
            handle=_unique_handle(session, identity.name),
            display_name=(identity.name or "Trader")[:80],
            cash=settings.starting_cash,
            starting_cash=settings.starting_cash,
        )
        session.add(profile)
        try:
            session.commit()
        except IntegrityError:
            # Two first requests raced; use the profile the other one created.
            session.rollback()
            profile = session.get(Profile, identity.user_id)
            if profile is None:
                raise
    return profile
