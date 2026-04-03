from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DatasetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    slug: str
    stream_seed: int


class BatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    stage: Literal["foundation"] = "foundation"
    master_seed: int
    count: int
    complexity_level: str
    default_tax_year: int
    note: str = (
        "Generation, reconciliation, and PDF rendering are not executed in this stage — "
        "this manifest records deterministic ids/seeds only."
    )
    datasets: list[DatasetPlan] = Field(default_factory=list)
