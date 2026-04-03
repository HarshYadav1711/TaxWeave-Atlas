from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FederalFormLines(BaseModel):
    """Subset of 1040-family lines represented in the sample pack; extend via `additional_lines`."""

    model_config = ConfigDict(extra="forbid")

    wages: int
    taxable_interest: int
    ordinary_dividends: int
    agi: int
    standard_deduction: int
    taxable_income: int
    total_tax: int
    federal_withholding: int
    additional_lines: dict[str, int] = Field(default_factory=dict)


class FederalReturn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: FederalFormLines
    # Future: attach authoritative form identifiers + version year when implementing PDF fill.
    form_references: list[str] = Field(default_factory=list)
