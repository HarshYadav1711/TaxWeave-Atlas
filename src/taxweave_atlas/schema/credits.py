from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    amount: int
    refundable: bool = False


class CreditsPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credits: list[CreditEntry] = Field(default_factory=list)
