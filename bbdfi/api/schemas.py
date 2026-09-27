from typing import Literal

from pydantic import BaseModel, Field


class OrderIn(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int = Field(ge=1, le=100_000)


class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rule_type: str
    params: dict
    active: bool = True


class StrategyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    active: bool | None = None


class BacktestIn(BaseModel):
    rule_type: str
    params: dict
    days: int = Field(default=90, ge=5, le=500)


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    handle: str | None = Field(default=None, pattern=r"^[a-z0-9_]{3,20}$")
