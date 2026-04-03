from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DatasetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    slug: str
    stream_seed: int
    tax_year: int | None = None
    state_code: str | None = None
    complexity_tier: str | None = None
    uniqueness_salt: int = 0
    case_fingerprint: str | None = None


class BatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    stage: str = "foundation"
    master_seed: int
    count: int
    complexity_level: str
    default_tax_year: int
    note: str = "Batch manifest."
    datasets: list[DatasetPlan] = Field(default_factory=list)
