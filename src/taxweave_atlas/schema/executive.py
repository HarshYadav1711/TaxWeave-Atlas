from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExecutiveSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agi: int
    taxable_income: int
    total_tax: int
    federal_withholding: int
    state_tax: int
    effective_rate_federal: float
