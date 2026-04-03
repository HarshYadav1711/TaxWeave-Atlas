from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StateAdjustments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    additions: int
    subtractions: int


class StateReturnLines(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_wages: int
    additions: int
    subtractions: int
    state_taxable_income: int
    state_tax: int
    additional_lines: dict[str, int] = Field(default_factory=dict)


class StateReturn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    adjustments: StateAdjustments
    lines: StateReturnLines
    tax_computed: int
    form_references: list[str] = Field(default_factory=list)
